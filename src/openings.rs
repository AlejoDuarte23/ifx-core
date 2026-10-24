use std::collections::BTreeMap;

use crate::{model::OpeningsData, relationships::Relations};

pub(crate) fn build_openings(relations: &Relations) -> OpeningsData {
    let mut openings_by_element = BTreeMap::new();
    let mut elements_by_opening = BTreeMap::new();
    let mut fillings_by_opening = BTreeMap::new();
    let mut openings_by_filling = BTreeMap::new();

    for relationship in &relations.voids {
        push_unique(
            &mut openings_by_element,
            relationship.element_id,
            relationship.opening_id,
        );
        push_unique(
            &mut elements_by_opening,
            relationship.opening_id,
            relationship.element_id,
        );
    }
    for relationship in &relations.fills {
        push_unique(
            &mut fillings_by_opening,
            relationship.opening_id,
            relationship.filling_id,
        );
        push_unique(
            &mut openings_by_filling,
            relationship.filling_id,
            relationship.opening_id,
        );
    }

    OpeningsData {
        voids: relations.voids.clone(),
        fills: relations.fills.clone(),
        openings_by_element,
        elements_by_opening,
        fillings_by_opening,
        openings_by_filling,
    }
}

fn push_unique(map: &mut BTreeMap<u32, Vec<u32>>, key: u32, value: u32) {
    let values = map.entry(key).or_default();
    if !values.contains(&value) {
        values.push(value);
        values.sort_unstable();
    }
}
