use std::collections::{BTreeMap, BTreeSet};

use crate::{
    model::{DerivedUnitElement, ResolvedUnit, UnitsData},
    parser::{enumeration, number, reference, refs, string, EntityRecord, ParsedModel},
};

pub(crate) fn build_units(model: &ParsedModel) -> UnitsData {
    let assignment_id = model
        .project_ids
        .first()
        .and_then(|project_id| model.records.get(project_id))
        .and_then(|project| reference(project.attributes.get(8)));
    let Some(assignment) = assignment_id.and_then(|id| model.records.get(&id)) else {
        return UnitsData {
            assignment_id,
            ..UnitsData::default()
        };
    };

    let mut resolver = UnitResolver {
        model,
        cache: BTreeMap::new(),
    };
    let mut by_type = BTreeMap::new();
    for unit_id in refs(assignment.attributes.first()) {
        if let Some(unit) = resolver.resolve(unit_id, &mut BTreeSet::new()) {
            by_type.entry(unit.unit_type.clone()).or_insert(unit);
        }
    }

    UnitsData {
        assignment_id,
        by_type,
    }
}

pub(crate) fn resolve_unit(model: &ParsedModel, unit_id: u32) -> Option<ResolvedUnit> {
    UnitResolver {
        model,
        cache: BTreeMap::new(),
    }
    .resolve(unit_id, &mut BTreeSet::new())
}

struct UnitResolver<'a> {
    model: &'a ParsedModel,
    cache: BTreeMap<u32, ResolvedUnit>,
}

impl UnitResolver<'_> {
    fn resolve(&mut self, unit_id: u32, visited: &mut BTreeSet<u32>) -> Option<ResolvedUnit> {
        if let Some(unit) = self.cache.get(&unit_id) {
            return Some(unit.clone());
        }
        if !visited.insert(unit_id) {
            return None;
        }
        let record = self.model.records.get(&unit_id)?.clone();
        let type_name = self.model.entity_types.get(&unit_id)?.as_str();
        let unit = match type_name {
            "IFCSIUNIT" => self.si_unit(&record),
            "IFCCONVERSIONBASEDUNIT" | "IFCCONVERSIONBASEDUNITWITHOFFSET" => {
                self.conversion_unit(&record, type_name, visited)
            }
            "IFCDERIVEDUNIT" => self.derived_unit(&record, visited),
            "IFCCONTEXTDEPENDENTUNIT" => self.context_dependent_unit(&record),
            "IFCMONETARYUNIT" => self.monetary_unit(&record),
            _ => None,
        }?;
        visited.remove(&unit_id);
        self.cache.insert(unit_id, unit.clone());
        Some(unit)
    }

    fn si_unit(&self, record: &EntityRecord) -> Option<ResolvedUnit> {
        let unit_type = enumeration(record.attributes.get(1))?;
        let prefix = enumeration(record.attributes.get(2));
        let name = enumeration(record.attributes.get(3))?;
        let (symbol, si_scale) = si_symbol_and_scale(&name, prefix.as_deref())?;
        Some(ResolvedUnit {
            express_id: record.id,
            ifc_type: "IfcSIUnit".to_string(),
            unit_type,
            name,
            symbol,
            si_scale: Some(si_scale),
            conversion_offset: None,
            elements: Vec::new(),
        })
    }

    fn conversion_unit(
        &mut self,
        record: &EntityRecord,
        type_name: &str,
        visited: &mut BTreeSet<u32>,
    ) -> Option<ResolvedUnit> {
        let unit_type = enumeration(record.attributes.get(1))?;
        let name = string(record.attributes.get(2))?;
        let scale = reference(record.attributes.get(3))
            .and_then(|factor_id| self.conversion_factor(factor_id, visited));
        Some(ResolvedUnit {
            express_id: record.id,
            ifc_type: if type_name == "IFCCONVERSIONBASEDUNITWITHOFFSET" {
                "IfcConversionBasedUnitWithOffset"
            } else {
                "IfcConversionBasedUnit"
            }
            .to_string(),
            unit_type,
            symbol: conversion_symbol(&name),
            name,
            si_scale: scale,
            conversion_offset: number(record.attributes.get(4)),
            elements: Vec::new(),
        })
    }

    fn conversion_factor(&mut self, factor_id: u32, visited: &mut BTreeSet<u32>) -> Option<f64> {
        let factor = self.model.records.get(&factor_id)?.clone();
        let value = number(factor.attributes.first())?;
        if !value.is_finite() || value <= 0.0 {
            return None;
        }
        let component_id = reference(factor.attributes.get(1))?;
        let component = self.resolve(component_id, visited)?;
        Some(value * component.si_scale?)
    }

    fn derived_unit(
        &mut self,
        record: &EntityRecord,
        visited: &mut BTreeSet<u32>,
    ) -> Option<ResolvedUnit> {
        let unit_type = enumeration(record.attributes.get(1))?;
        let mut elements = Vec::new();
        let mut composed = Vec::new();
        let mut scale = Some(1.0_f64);
        for element_id in refs(record.attributes.first()) {
            let element_record = self.model.records.get(&element_id)?.clone();
            let unit_id = reference(element_record.attributes.first())?;
            let exponent = number(element_record.attributes.get(1))? as i64;
            let component = self.resolve(unit_id, visited)?;
            if let (Some(total), Some(component_scale)) = (scale, component.si_scale) {
                scale = Some(total * component_scale.powi(exponent as i32));
            } else {
                scale = None;
            }
            composed.push((component.symbol.clone(), exponent));
            elements.push(DerivedUnitElement {
                express_id: element_id,
                unit_id,
                exponent,
                symbol: component.symbol,
                si_scale: component.si_scale,
            });
        }
        let symbol = compose_derived(&composed);
        if symbol.is_empty() {
            return None;
        }
        let name = string(record.attributes.get(2)).unwrap_or_else(|| unit_type.clone());
        Some(ResolvedUnit {
            express_id: record.id,
            ifc_type: "IfcDerivedUnit".to_string(),
            unit_type,
            name,
            symbol,
            si_scale: scale,
            conversion_offset: None,
            elements,
        })
    }

    fn context_dependent_unit(&self, record: &EntityRecord) -> Option<ResolvedUnit> {
        let unit_type = enumeration(record.attributes.get(1))?;
        let name = string(record.attributes.get(2))?;
        Some(ResolvedUnit {
            express_id: record.id,
            ifc_type: "IfcContextDependentUnit".to_string(),
            unit_type,
            symbol: name.clone(),
            name,
            si_scale: None,
            conversion_offset: None,
            elements: Vec::new(),
        })
    }

    fn monetary_unit(&self, record: &EntityRecord) -> Option<ResolvedUnit> {
        let name =
            string(record.attributes.first()).or_else(|| enumeration(record.attributes.first()))?;
        Some(ResolvedUnit {
            express_id: record.id,
            ifc_type: "IfcMonetaryUnit".to_string(),
            unit_type: "MONETARYUNIT".to_string(),
            symbol: currency_symbol(&name),
            name,
            si_scale: Some(1.0),
            conversion_offset: None,
            elements: Vec::new(),
        })
    }
}

fn si_symbol_and_scale(name: &str, prefix: Option<&str>) -> Option<(String, f64)> {
    let (base_symbol, prefix_power, base_scale) = match name {
        "METRE" => ("m", 1, 1.0),
        "SQUARE_METRE" => ("m²", 2, 1.0),
        "CUBIC_METRE" => ("m³", 3, 1.0),
        "GRAM" => ("g", 1, 1e-3),
        "SECOND" => ("s", 1, 1.0),
        "AMPERE" => ("A", 1, 1.0),
        "KELVIN" => ("K", 1, 1.0),
        "MOLE" => ("mol", 1, 1.0),
        "CANDELA" => ("cd", 1, 1.0),
        "RADIAN" => ("rad", 1, 1.0),
        "STERADIAN" => ("sr", 1, 1.0),
        "HERTZ" => ("Hz", 1, 1.0),
        "NEWTON" => ("N", 1, 1.0),
        "PASCAL" => ("Pa", 1, 1.0),
        "JOULE" => ("J", 1, 1.0),
        "WATT" => ("W", 1, 1.0),
        "COULOMB" => ("C", 1, 1.0),
        "VOLT" => ("V", 1, 1.0),
        "FARAD" => ("F", 1, 1.0),
        "OHM" => ("Ω", 1, 1.0),
        "SIEMENS" => ("S", 1, 1.0),
        "WEBER" => ("Wb", 1, 1.0),
        "TESLA" => ("T", 1, 1.0),
        "HENRY" => ("H", 1, 1.0),
        "DEGREE_CELSIUS" => ("°C", 1, 1.0),
        "LUMEN" => ("lm", 1, 1.0),
        "LUX" => ("lx", 1, 1.0),
        "BECQUEREL" => ("Bq", 1, 1.0),
        "GRAY" => ("Gy", 1, 1.0),
        "SIEVERT" => ("Sv", 1, 1.0),
        _ => return None,
    };
    let prefix_scale = prefix.map(prefix_multiplier).unwrap_or(1.0);
    let prefix_symbol = prefix.map(prefix_symbol).unwrap_or_default();
    Some((
        format!("{prefix_symbol}{base_symbol}"),
        base_scale * prefix_scale.powi(prefix_power),
    ))
}

fn prefix_multiplier(prefix: &str) -> f64 {
    match prefix {
        "EXA" => 1e18,
        "PETA" => 1e15,
        "TERA" => 1e12,
        "GIGA" => 1e9,
        "MEGA" => 1e6,
        "KILO" => 1e3,
        "HECTO" => 1e2,
        "DECA" => 1e1,
        "DECI" => 1e-1,
        "CENTI" => 1e-2,
        "MILLI" => 1e-3,
        "MICRO" => 1e-6,
        "NANO" => 1e-9,
        "PICO" => 1e-12,
        "FEMTO" => 1e-15,
        "ATTO" => 1e-18,
        _ => 1.0,
    }
}

fn prefix_symbol(prefix: &str) -> &'static str {
    match prefix {
        "EXA" => "E",
        "PETA" => "P",
        "TERA" => "T",
        "GIGA" => "G",
        "MEGA" => "M",
        "KILO" => "k",
        "HECTO" => "h",
        "DECA" => "da",
        "DECI" => "d",
        "CENTI" => "c",
        "MILLI" => "m",
        "MICRO" => "µ",
        "NANO" => "n",
        "PICO" => "p",
        "FEMTO" => "f",
        "ATTO" => "a",
        _ => "",
    }
}

fn conversion_symbol(name: &str) -> String {
    match name.trim_matches('\'').trim().to_ascii_uppercase().as_str() {
        "DEGREE" => "°",
        "GRAD" | "GON" => "gon",
        "MINUTE" => "′",
        "SECOND" => "″",
        "FOOT" | "FEET" => "ft",
        "INCH" | "INCHES" => "in",
        "YARD" => "yd",
        "MILE" => "mi",
        "LITRE" | "LITER" => "L",
        "ACRE" => "acre",
        "POUND" | "POUND-MASS" | "LBM" => "lb",
        "POUND-FORCE" | "LBF" => "lbf",
        "OUNCE" => "oz",
        "TON-METRIC" | "TONNE" => "t",
        "PSI" => "psi",
        "BAR" => "bar",
        "KIP" => "kip",
        "MINUTE-TIME" | "MIN" => "min",
        "HOUR" => "h",
        "DAY" => "d",
        "BTU" => "Btu",
        _ => name,
    }
    .to_string()
}

fn currency_symbol(name: &str) -> String {
    match name
        .trim_matches(['\'', '.'])
        .trim()
        .to_ascii_uppercase()
        .as_str()
    {
        "EUR" => "€",
        "USD" => "$",
        "GBP" => "£",
        "JPY" | "CNY" | "RMB" => "¥",
        _ => name,
    }
    .to_string()
}

fn compose_derived(elements: &[(String, i64)]) -> String {
    let mut numerator = Vec::new();
    let mut denominator = Vec::new();
    for (symbol, exponent) in elements {
        if *exponent == 0 || symbol.is_empty() {
            continue;
        }
        let part = format!("{}{}", symbol, superscript(exponent.unsigned_abs()));
        if *exponent > 0 {
            numerator.push(part);
        } else {
            denominator.push(part);
        }
    }
    let numerator = if numerator.is_empty() {
        "1".to_string()
    } else {
        numerator.join("·")
    };
    match denominator.len() {
        0 if numerator == "1" => String::new(),
        0 => numerator,
        1 => format!("{numerator}/{}", denominator[0]),
        _ => format!("{numerator}/({})", denominator.join("·")),
    }
}

fn superscript(value: u64) -> String {
    if value == 1 {
        return String::new();
    }
    value
        .to_string()
        .chars()
        .map(|character| match character {
            '0' => '⁰',
            '1' => '¹',
            '2' => '²',
            '3' => '³',
            '4' => '⁴',
            '5' => '⁵',
            '6' => '⁶',
            '7' => '⁷',
            '8' => '⁸',
            '9' => '⁹',
            other => other,
        })
        .collect()
}
