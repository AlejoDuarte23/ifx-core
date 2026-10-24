mod header;
#[path = "generated/ifc2x3.rs"]
mod ifc2x3;
#[path = "generated/ifc4.rs"]
mod ifc4;
#[path = "generated/ifc4x3_add2.rs"]
mod ifc4x3_add2;
#[path = "generated/ifc4x3_rc4.rs"]
mod ifc4x3_rc4;

pub use header::declared_schema;

#[derive(Debug)]
pub struct EntityDefinition {
    pub step_name: &'static str,
    pub name: &'static str,
    pub parent: Option<&'static str>,
    pub attributes: &'static [&'static str],
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SourceSchema {
    Ifc2x3,
    Ifc4,
    Ifc4x3Rc4,
    Ifc4x3Add2,
}

impl SourceSchema {
    pub fn from_identifier(identifier: &str) -> Option<Self> {
        match identifier.to_ascii_uppercase().as_str() {
            "IFC2X3" | "IFC2X3_TC1" => Some(Self::Ifc2x3),
            "IFC4" | "IFC4_ADD2" | "IFC4_ADD2_TC1" => Some(Self::Ifc4),
            "IFC4X3_RC4" => Some(Self::Ifc4x3Rc4),
            "IFC4X3" | "IFC4X3_ADD2" => Some(Self::Ifc4x3Add2),
            _ => None,
        }
    }

    pub fn family(self) -> &'static str {
        match self {
            Self::Ifc2x3 => "IFC2X3",
            Self::Ifc4 => "IFC4",
            Self::Ifc4x3Rc4 | Self::Ifc4x3Add2 => "IFC4X3",
        }
    }

    pub fn entities(self) -> &'static [EntityDefinition] {
        match self {
            Self::Ifc2x3 => ifc2x3::ENTITIES,
            Self::Ifc4 => ifc4::ENTITIES,
            Self::Ifc4x3Rc4 => ifc4x3_rc4::ENTITIES,
            Self::Ifc4x3Add2 => ifc4x3_add2::ENTITIES,
        }
    }

    pub fn entity(self, step_name: &str) -> Option<&'static EntityDefinition> {
        let step_name = step_name.trim();
        let entities = self.entities();
        // The scanner returns the original STEP spelling. Uppercase only when needed.
        let upper;
        let name = if step_name.bytes().any(|b| b.is_ascii_lowercase()) {
            upper = step_name.to_ascii_uppercase();
            upper.as_str()
        } else {
            step_name
        };
        entities
            .binary_search_by_key(&name, |e| e.step_name)
            .ok()
            .map(|i| &entities[i])
    }

    pub fn is_subtype(self, step_name: &str, base: &str) -> bool {
        let mut next = self.entity(step_name);
        while let Some(entity) = next {
            if entity.step_name.eq_ignore_ascii_case(base) {
                return true;
            }
            next = entity.parent.and_then(|name| self.entity(name));
        }
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn source_layouts_and_identity_are_separate_from_routing() {
        let old = SourceSchema::Ifc2x3;
        assert_eq!(
            old.entity("IFCSPACE").unwrap().attributes[9],
            "InteriorOrExteriorSpace"
        );
        assert_eq!(old.entity("IFCDOORSTYLE").unwrap().name, "IfcDoorStyle");
        assert!(old.is_subtype("IFCELECTRICDISTRIBUTIONPOINT", "IFCPRODUCT"));
        assert_eq!(
            old.entity("IFCGRIDPLACEMENT").unwrap().attributes[0],
            "PlacementLocation"
        );
        assert_eq!(
            SourceSchema::Ifc4x3Add2
                .entity("IFCGRIDPLACEMENT")
                .unwrap()
                .attributes[0],
            "PlacementRelTo"
        );
        assert!(SourceSchema::from_identifier("IFC4X3_FAKE").is_none());
    }
}
