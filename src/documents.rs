use std::collections::{BTreeMap, BTreeSet};

use crate::{
    model::{DocumentDefinition, DocumentsData, ElementDocumentAssignment},
    parser::{enumeration, reference, string, ParsedModel},
    relationships::Relations,
};

pub(crate) fn build_documents(model: &ParsedModel, relations: &Relations) -> DocumentsData {
    let information: BTreeMap<u32, DocumentDefinition> = model
        .entity_types
        .iter()
        .filter_map(|(id, type_name)| {
            if type_name != "IFCDOCUMENTINFORMATION" {
                return None;
            }
            let record = model.records.get(id)?;
            Some((
                *id,
                DocumentDefinition {
                    express_id: *id,
                    document_type: "DocumentInformation".to_string(),
                    referenced_document_id: None,
                    identification: string(
                        record
                            .get("Identification")
                            .or_else(|| record.get("DocumentId")),
                    ),
                    name: string(record.get("Name")),
                    description: string(record.get("Description")),
                    location: string(record.get("Location")),
                    purpose: string(record.get("Purpose")),
                    intended_use: string(record.get("IntendedUse")),
                    scope: string(record.get("Scope")),
                    revision: string(record.get("Revision")),
                    electronic_format: document_format(model, record.get("ElectronicFormat")),
                    valid_from: document_date(model, record.get("ValidFrom")),
                    valid_until: document_date(model, record.get("ValidUntil")),
                    confidentiality: enumeration(record.get("Confidentiality")),
                    status: enumeration(record.get("Status")),
                },
            ))
        })
        .collect();

    let mut definitions = information.clone();
    for (id, type_name) in &model.entity_types {
        if type_name != "IFCDOCUMENTREFERENCE" {
            continue;
        }
        let Some(record) = model.records.get(id) else {
            continue;
        };
        let referenced_document_id = reference(record.get("ReferencedDocument"));
        let inherited = referenced_document_id.and_then(|doc_id| information.get(&doc_id));
        definitions.insert(
            *id,
            DocumentDefinition {
                express_id: *id,
                document_type: "DocumentReference".to_string(),
                referenced_document_id,
                identification: string(
                    record
                        .get("Identification")
                        .or_else(|| record.get("ItemReference")),
                )
                .or_else(|| inherited.and_then(|doc| doc.identification.clone())),
                name: string(record.get("Name"))
                    .or_else(|| inherited.and_then(|doc| doc.name.clone())),
                description: string(record.get("Description"))
                    .or_else(|| inherited.and_then(|doc| doc.description.clone())),
                location: string(record.get("Location"))
                    .or_else(|| inherited.and_then(|doc| doc.location.clone())),
                purpose: inherited.and_then(|doc| doc.purpose.clone()),
                intended_use: inherited.and_then(|doc| doc.intended_use.clone()),
                scope: inherited.and_then(|doc| doc.scope.clone()),
                revision: inherited.and_then(|doc| doc.revision.clone()),
                electronic_format: inherited.and_then(|doc| doc.electronic_format.clone()),
                valid_from: inherited.and_then(|doc| doc.valid_from.clone()),
                valid_until: inherited.and_then(|doc| doc.valid_until.clone()),
                confidentiality: inherited.and_then(|doc| doc.confidentiality.clone()),
                status: inherited.and_then(|doc| doc.status.clone()),
            },
        );
    }

    let mut own: BTreeMap<u32, Vec<(u32, u32)>> = BTreeMap::new();
    for association in &relations.document_associations {
        for object_id in &association.related_objects {
            own.entry(*object_id)
                .or_default()
                .push((association.relationship_id, association.document_id));
        }
    }
    for assignments in own.values_mut() {
        assignments.sort_unstable();
        assignments.dedup();
    }

    let candidate_ids: BTreeSet<u32> = own
        .keys()
        .filter(|id| !is_type_like(model.entity_types.get(id).map(String::as_str)))
        .copied()
        .chain(relations.defines_type.keys().copied())
        .collect();
    let mut element_documents = BTreeMap::new();
    for entity_id in candidate_ids {
        let mut assignments = Vec::new();
        let mut seen = BTreeSet::new();
        append_assignments(
            own.get(&entity_id),
            None,
            &definitions,
            &mut seen,
            &mut assignments,
        );
        for (_, type_id) in relations.defines_type.get(&entity_id).into_iter().flatten() {
            append_assignments(
                own.get(type_id),
                Some(*type_id),
                &definitions,
                &mut seen,
                &mut assignments,
            );
        }
        if !assignments.is_empty() {
            element_documents.insert(entity_id, assignments);
        }
    }

    DocumentsData {
        definitions,
        associations: relations.document_associations.clone(),
        element_documents,
    }
}

fn append_assignments(
    source: Option<&Vec<(u32, u32)>>,
    inherited_from_type: Option<u32>,
    definitions: &BTreeMap<u32, DocumentDefinition>,
    seen: &mut BTreeSet<u32>,
    output: &mut Vec<ElementDocumentAssignment>,
) {
    for (_, document_id) in source.into_iter().flatten() {
        if !seen.insert(*document_id) {
            continue;
        }
        let Some(document) = definitions.get(document_id) else {
            continue;
        };
        output.push(ElementDocumentAssignment {
            definition_id: *document_id,
            inherited_from_type,
            document: document.clone(),
        });
    }
}

fn is_type_like(type_name: Option<&str>) -> bool {
    type_name.is_some_and(|value| value.ends_with("TYPE") || value.ends_with("STYLE"))
}

fn document_format(
    model: &ParsedModel,
    value: Option<&ifx_step::AttributeValue>,
) -> Option<String> {
    string(value).or_else(|| {
        let record = model.records.get(&reference(value)?)?;
        string(record.get("MimeContentType"))
            .map(|mime| {
                string(record.get("MimeSubtype"))
                    .map_or_else(|| mime.clone(), |subtype| format!("{mime}/{subtype}"))
            })
            .or_else(|| string(record.get("FileExtension")))
    })
}

pub(crate) fn document_date(
    model: &ParsedModel,
    value: Option<&ifx_step::AttributeValue>,
) -> Option<String> {
    string(value).or_else(|| {
        let mut record = model.records.get(&reference(value)?)?;
        if record.ifc_type == "IfcDateAndTime" {
            record = model
                .records
                .get(&reference(record.get("DateComponent"))?)?;
        }
        if record.ifc_type != "IfcCalendarDate" {
            return None;
        }
        let number = |name| crate::parser::number(record.get(name)).map(|n| n as i32);
        Some(format!(
            "{:04}-{:02}-{:02}",
            number("YearComponent")?,
            number("MonthComponent")?,
            number("DayComponent")?
        ))
    })
}
