use std::collections::{BTreeMap, BTreeSet};

use crate::{
    model::{
        ElementMaterialAssignment, MaterialConstituent, MaterialLayer, MaterialLeaf,
        MaterialProfile, MaterialsData, ResolvedMaterial,
    },
    parser::{boolean, number, reference, refs, string, EntityRecord, ParsedModel},
    relationships::Relations,
};

pub(crate) fn build_materials(
    model: &ParsedModel,
    relations: &Relations,
    bytes: &[u8],
) -> MaterialsData {
    let mut own: BTreeMap<u32, Vec<(u32, u32)>> = BTreeMap::new();
    for association in &relations.material_associations {
        for object_id in &association.related_objects {
            own.entry(*object_id).or_default().push((
                association.relationship_id,
                association.relating_material_id,
            ));
        }
    }
    for assignments in own.values_mut() {
        assignments.sort_unstable_by_key(|(relationship_id, _)| *relationship_id);
        let mut seen_definitions = BTreeSet::new();
        assignments.retain(|(_, definition_id)| seen_definitions.insert(*definition_id));
    }

    let mut resolver = MaterialResolver {
        model,
        cache: BTreeMap::new(),
    };
    let mut element_materials = BTreeMap::new();
    let candidate_ids: BTreeSet<u32> = own
        .keys()
        .filter(|id| !is_type_like(model.entity_types.get(id).map(String::as_str)))
        .copied()
        .chain(relations.defines_type.keys().copied())
        .collect();

    for entity_id in candidate_ids {
        let (assignments, inherited_from_type) = if let Some(assignments) = own.get(&entity_id) {
            (assignments.clone(), None)
        } else {
            let mut inherited = None;
            let mut found = Vec::new();
            for (_, type_id) in relations.defines_type.get(&entity_id).into_iter().flatten() {
                if let Some(type_assignments) = own.get(type_id) {
                    inherited = Some(*type_id);
                    found = type_assignments.clone();
                    break;
                }
            }
            (found, inherited)
        };

        let mut resolved = Vec::new();
        for (_, definition_id) in assignments {
            if let Some(material) = resolver.resolve(definition_id, &mut BTreeSet::new()) {
                resolved.push(ElementMaterialAssignment {
                    definition_id,
                    inherited_from_type,
                    material,
                });
            }
        }
        if !resolved.is_empty() {
            element_materials.insert(entity_id, resolved);
        }
    }

    // Surface every independently resolvable top-level definition, not only
    // definitions reached by an association. Nested layers/profiles/
    // constituents remain embedded in their owning set.
    let definition_ids: Vec<u32> = model
        .entity_types
        .iter()
        .filter_map(|(id, type_name)| is_material_definition(type_name).then_some(*id))
        .collect();
    for definition_id in definition_ids {
        let _ = resolver.resolve(definition_id, &mut BTreeSet::new());
    }

    let (property_sets, properties_by_material, properties_by_profile) =
        crate::resource_properties::extract(model, bytes);
    MaterialsData {
        property_sets,
        properties_by_material,
        properties_by_profile,
        associations: relations.material_associations.clone(),
        definitions: resolver.cache,
        element_materials,
    }
}

fn is_type_like(type_name: Option<&str>) -> bool {
    type_name.is_some_and(|value| value.ends_with("TYPE") || value.ends_with("STYLE"))
}

fn is_material_definition(type_name: &str) -> bool {
    matches!(
        type_name,
        "IFCMATERIAL"
            | "IFCMATERIALLAYERSET"
            | "IFCMATERIALLAYERSETUSAGE"
            | "IFCMATERIALPROFILESET"
            | "IFCMATERIALPROFILESETUSAGE"
            | "IFCMATERIALCONSTITUENTSET"
            | "IFCMATERIALLIST"
    )
}

struct MaterialResolver<'a> {
    model: &'a ParsedModel,
    cache: BTreeMap<u32, ResolvedMaterial>,
}

impl MaterialResolver<'_> {
    fn resolve(
        &mut self,
        definition_id: u32,
        visited: &mut BTreeSet<u32>,
    ) -> Option<ResolvedMaterial> {
        if let Some(cached) = self.cache.get(&definition_id) {
            return Some(cached.clone());
        }
        if !visited.insert(definition_id) {
            return None;
        }
        let record = self.model.records.get(&definition_id)?.clone();
        let type_upper = self.model.entity_types.get(&definition_id)?.as_str();

        let mut result = match type_upper {
            "IFCMATERIAL" => self.resolve_plain(&record),
            "IFCMATERIALLAYERSET" => self.resolve_layer_set(&record),
            "IFCMATERIALPROFILESET" => self.resolve_profile_set(&record),
            "IFCMATERIALCONSTITUENTSET" => self.resolve_constituent_set(&record),
            "IFCMATERIALLIST" => self.resolve_list(&record),
            "IFCMATERIALLAYERSETUSAGE" | "IFCMATERIALPROFILESETUSAGE" => {
                let target_id = reference(record.attributes.first())?;
                let mut nested = self.resolve(target_id, visited)?;
                nested.source_definition_id = definition_id;
                nested
            }
            _ => return None,
        };
        result.source_definition_id = definition_id;
        visited.remove(&definition_id);
        self.cache.insert(definition_id, result.clone());
        Some(result)
    }

    fn resolve_plain(&self, record: &EntityRecord) -> ResolvedMaterial {
        ResolvedMaterial {
            source_definition_id: record.id,
            resolved_definition_id: record.id,
            material_type: "Material".to_string(),
            name: string(record.attributes.first()),
            description: string(record.attributes.get(1)),
            category: string(record.attributes.get(2)),
            layers: Vec::new(),
            profiles: Vec::new(),
            constituents: Vec::new(),
            materials: Vec::new(),
        }
    }

    fn resolve_layer_set(&self, record: &EntityRecord) -> ResolvedMaterial {
        let mut layers = Vec::new();
        for layer_id in refs(record.attributes.first()) {
            let Some(layer) = self.model.records.get(&layer_id) else {
                continue;
            };
            let material_id = reference(layer.attributes.first());
            let (material_name, material_category) = self.material_name_category(material_id);
            layers.push(MaterialLayer {
                express_id: layer_id,
                material_id,
                material_name,
                material_category,
                thickness: number(layer.attributes.get(1))
                    .map(|value| value * self.model.length_unit_scale),
                is_ventilated: boolean(layer.attributes.get(2)),
                name: string(layer.attributes.get(3)),
                description: string(layer.attributes.get(4)),
                category: string(layer.attributes.get(5)),
                priority: number(layer.attributes.get(6)),
            });
        }
        ResolvedMaterial {
            source_definition_id: record.id,
            resolved_definition_id: record.id,
            material_type: "MaterialLayerSet".to_string(),
            name: string(record.attributes.get(1)),
            description: string(record.attributes.get(2)),
            category: None,
            layers,
            profiles: Vec::new(),
            constituents: Vec::new(),
            materials: Vec::new(),
        }
    }

    fn resolve_profile_set(&self, record: &EntityRecord) -> ResolvedMaterial {
        let mut profiles = Vec::new();
        for profile_id in refs(record.attributes.get(2)) {
            let Some(profile) = self.model.records.get(&profile_id) else {
                continue;
            };
            let material_id = reference(profile.attributes.get(2));
            let (material_name, material_category) = self.material_name_category(material_id);
            profiles.push(MaterialProfile {
                express_id: profile_id,
                material_id,
                material_name,
                material_category,
                profile_id: reference(profile.attributes.get(3)),
                name: string(profile.attributes.first()),
                description: string(profile.attributes.get(1)),
                category: string(profile.attributes.get(5)),
                priority: number(profile.attributes.get(4)),
            });
        }
        ResolvedMaterial {
            source_definition_id: record.id,
            resolved_definition_id: record.id,
            material_type: "MaterialProfileSet".to_string(),
            name: string(record.attributes.first()),
            description: string(record.attributes.get(1)),
            category: None,
            layers: Vec::new(),
            profiles,
            constituents: Vec::new(),
            materials: Vec::new(),
        }
    }

    fn resolve_constituent_set(&self, record: &EntityRecord) -> ResolvedMaterial {
        let mut constituents = Vec::new();
        for constituent_id in refs(record.attributes.get(2)) {
            let Some(constituent) = self.model.records.get(&constituent_id) else {
                continue;
            };
            let material_id = reference(constituent.attributes.get(2));
            let (material_name, material_category) = self.material_name_category(material_id);
            constituents.push(MaterialConstituent {
                express_id: constituent_id,
                material_id,
                material_name,
                material_category,
                name: string(constituent.attributes.first()),
                description: string(constituent.attributes.get(1)),
                fraction: number(constituent.attributes.get(3)),
                category: string(constituent.attributes.get(4)),
            });
        }
        ResolvedMaterial {
            source_definition_id: record.id,
            resolved_definition_id: record.id,
            material_type: "MaterialConstituentSet".to_string(),
            name: string(record.attributes.first()),
            description: string(record.attributes.get(1)),
            category: None,
            layers: Vec::new(),
            profiles: Vec::new(),
            constituents,
            materials: Vec::new(),
        }
    }

    fn resolve_list(&self, record: &EntityRecord) -> ResolvedMaterial {
        let materials = refs(record.attributes.first())
            .into_iter()
            .map(|material_id| {
                let (name, category) = self.material_name_category(Some(material_id));
                MaterialLeaf {
                    express_id: material_id,
                    name: name.unwrap_or_else(|| format!("Material #{}", material_id)),
                    category,
                }
            })
            .collect();
        ResolvedMaterial {
            source_definition_id: record.id,
            resolved_definition_id: record.id,
            material_type: "MaterialList".to_string(),
            name: None,
            description: None,
            category: None,
            layers: Vec::new(),
            profiles: Vec::new(),
            constituents: Vec::new(),
            materials,
        }
    }

    fn material_name_category(&self, material_id: Option<u32>) -> (Option<String>, Option<String>) {
        let Some(record) = material_id.and_then(|id| self.model.records.get(&id)) else {
            return (None, None);
        };
        (
            string(record.attributes.first()),
            string(record.attributes.get(2)),
        )
    }
}
