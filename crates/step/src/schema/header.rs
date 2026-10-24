// Read header tokens without interpreting text inside STEP strings or comments.
// A bounded scan prevents malformed files from forcing a full model scan per decoder.
pub fn declared_schema(bytes: &[u8]) -> Option<String> {
    let bytes = &bytes[..bytes.len().min(1024 * 1024)];
    let mut cursor = 0;
    while cursor < bytes.len() {
        skip_space(bytes, &mut cursor)?;
        let b = *bytes.get(cursor)?;
        if b == b'\'' {
            read_string(bytes, &mut cursor)?;
            continue;
        }
        if b.is_ascii_alphabetic() || b == b'_' {
            let start = cursor;
            while bytes
                .get(cursor)
                .is_some_and(|b| b.is_ascii_alphanumeric() || *b == b'_')
            {
                cursor += 1;
            }
            let token = &bytes[start..cursor];
            if token.eq_ignore_ascii_case(b"ENDSEC") || token.eq_ignore_ascii_case(b"DATA") {
                return None;
            }
            if token.eq_ignore_ascii_case(b"FILE_SCHEMA") {
                for expected in b"((" {
                    expect(bytes, &mut cursor, *expected)?;
                }
                skip_space(bytes, &mut cursor)?;
                let schema = read_string(bytes, &mut cursor)?;
                for expected in b"));" {
                    expect(bytes, &mut cursor, *expected)?;
                }
                return Some(schema.to_ascii_uppercase());
            }
        } else {
            cursor += 1;
        }
    }
    None
}

fn skip_space(bytes: &[u8], cursor: &mut usize) -> Option<()> {
    loop {
        while bytes.get(*cursor).is_some_and(u8::is_ascii_whitespace) {
            *cursor += 1;
        }
        if bytes.get(*cursor..*cursor + 2) == Some(b"/*") {
            *cursor += 2;
            while bytes.get(*cursor..*cursor + 2) != Some(b"*/") {
                bytes.get(*cursor)?;
                *cursor += 1;
            }
            *cursor += 2;
        } else {
            return Some(());
        }
    }
}

fn expect(bytes: &[u8], cursor: &mut usize, expected: u8) -> Option<()> {
    skip_space(bytes, cursor)?;
    if bytes.get(*cursor) != Some(&expected) {
        return None;
    }
    *cursor += 1;
    Some(())
}

fn read_string(bytes: &[u8], cursor: &mut usize) -> Option<String> {
    if bytes.get(*cursor) != Some(&b'\'') {
        return None;
    }
    *cursor += 1;
    let mut value = Vec::new();
    loop {
        let b = *bytes.get(*cursor)?;
        *cursor += 1;
        if b == b'\'' {
            if bytes.get(*cursor) == Some(&b'\'') {
                *cursor += 1;
                value.push(b);
            } else {
                return String::from_utf8(value).ok();
            }
        } else {
            value.push(b);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn reads_only_the_real_declaration() {
        let source = b"HEADER;FILE_DESCRIPTION(('FILE_SCHEMA((''IFC4X3_FAKE'')); ENDSEC;'), '2;1'); /* FILE_SCHEMA(('IFC4')); */ FILE_SCHEMA ( ( 'IFC2X3' ) );ENDSEC;";
        assert_eq!(declared_schema(source).as_deref(), Some("IFC2X3"));
        assert_eq!(
            declared_schema(b"HEADER;FILE_SCHEMA(('IFC4X3_FAKE'));ENDSEC;").as_deref(),
            Some("IFC4X3_FAKE")
        );
        assert_eq!(
            declared_schema(b"HEADER;FILE_SCHEMA(('IFC4','IFC2X3'));ENDSEC;"),
            None
        );
        assert_eq!(
            declared_schema(b"HEADER;ENDSEC;DATA;#1=IFCPROJECT('IFC4');"),
            None
        );
        assert_eq!(declared_schema(b"HEADER;/* unfinished"), None);
    }
}
