use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ModelData {
    pub schema: Option<String>,
    pub entity_count: usize,
    pub length_unit_scale: f64,
    pub units: UnitsData,
    pub relationships: RelationshipData,
    #[serde(default)]
    pub object_types: ObjectTypesData,
    pub spatial: SpatialData,
    pub openings: OpeningsData,
    pub classifications: ClassificationsData,
    pub documents: DocumentsData,
    pub groups: GroupsData,
    pub connections: ConnectionsData,
    pub georeferencing: GeoreferencingData,
    pub materials: MaterialsData,
    pub coverage: crate::CoverageReport,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct UnitsData {
    pub assignment_id: Option<u32>,
    pub by_type: BTreeMap<String, ResolvedUnit>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ResolvedUnit {
    pub express_id: u32,
    pub ifc_type: String,
    pub unit_type: String,
    pub name: String,
    pub symbol: String,
    pub si_scale: Option<f64>,
    pub conversion_offset: Option<f64>,
    pub elements: Vec<DerivedUnitElement>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DerivedUnitElement {
    pub express_id: u32,
    pub unit_id: u32,
    pub exponent: i64,
    pub symbol: String,
    pub si_scale: Option<f64>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct RelationshipData {
    pub edges: Vec<RelationshipEdge>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RelationshipEdge {
    pub relationship_id: u32,
    pub relationship_type: String,
    pub relating_id: u32,
    pub related_id: u32,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct ObjectTypesData {
    pub definitions: BTreeMap<u32, ObjectTypeDefinition>,
    pub types_by_element: BTreeMap<u32, Vec<u32>>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ObjectTypeDefinition {
    pub express_id: u32,
    pub ifc_type: String,
    pub global_id: Option<String>,
    pub name: Option<String>,
    pub description: Option<String>,
    pub attributes: Vec<ifx_entities::PropValue>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct OpeningsData {
    pub voids: Vec<VoidRelationship>,
    pub fills: Vec<FillRelationship>,
    pub openings_by_element: BTreeMap<u32, Vec<u32>>,
    pub elements_by_opening: BTreeMap<u32, Vec<u32>>,
    pub fillings_by_opening: BTreeMap<u32, Vec<u32>>,
    pub openings_by_filling: BTreeMap<u32, Vec<u32>>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VoidRelationship {
    pub relationship_id: u32,
    pub element_id: u32,
    pub opening_id: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FillRelationship {
    pub relationship_id: u32,
    pub opening_id: u32,
    pub filling_id: u32,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct ClassificationsData {
    pub systems: BTreeMap<u32, ClassificationSystem>,
    pub references: BTreeMap<u32, ClassificationReference>,
    pub associations: Vec<ClassificationAssociation>,
    pub element_classifications: BTreeMap<u32, Vec<ElementClassificationAssignment>>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ClassificationSystem {
    pub express_id: u32,
    pub source: Option<String>,
    pub edition: Option<String>,
    pub edition_date: Option<String>,
    pub name: String,
    pub description: Option<String>,
    pub location: Option<String>,
    pub reference_tokens: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ClassificationReference {
    pub express_id: u32,
    pub location: Option<String>,
    pub identification: Option<String>,
    pub name: Option<String>,
    pub referenced_source_id: Option<u32>,
    pub description: Option<String>,
    pub sort: Option<String>,
    pub system_id: Option<u32>,
    pub system_name: Option<String>,
    pub path: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ClassificationAssociation {
    pub relationship_id: u32,
    pub classification_id: u32,
    pub related_objects: Vec<u32>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ElementClassificationAssignment {
    pub classification_id: u32,
    pub inherited_from_type: Option<u32>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct DocumentsData {
    pub definitions: BTreeMap<u32, DocumentDefinition>,
    pub associations: Vec<DocumentAssociation>,
    pub element_documents: BTreeMap<u32, Vec<ElementDocumentAssignment>>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DocumentDefinition {
    pub express_id: u32,
    pub document_type: String,
    pub referenced_document_id: Option<u32>,
    pub identification: Option<String>,
    pub name: Option<String>,
    pub description: Option<String>,
    pub location: Option<String>,
    pub purpose: Option<String>,
    pub intended_use: Option<String>,
    pub scope: Option<String>,
    pub revision: Option<String>,
    pub electronic_format: Option<String>,
    pub valid_from: Option<String>,
    pub valid_until: Option<String>,
    pub confidentiality: Option<String>,
    pub status: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DocumentAssociation {
    pub relationship_id: u32,
    pub document_id: u32,
    pub related_objects: Vec<u32>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ElementDocumentAssignment {
    pub definition_id: u32,
    pub inherited_from_type: Option<u32>,
    pub document: DocumentDefinition,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct GroupsData {
    pub definitions: BTreeMap<u32, GroupDefinition>,
    pub memberships: Vec<GroupMembership>,
    pub groups_by_object: BTreeMap<u32, Vec<GroupMembership>>,
    pub members_by_group: BTreeMap<u32, Vec<GroupMembership>>,
    pub product_assignments: Vec<ProductAssignment>,
    pub products_by_object: BTreeMap<u32, Vec<u32>>,
    pub objects_by_product: BTreeMap<u32, Vec<u32>>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GroupDefinition {
    pub express_id: u32,
    pub ifc_type: String,
    pub global_id: Option<String>,
    pub name: Option<String>,
    pub description: Option<String>,
    pub object_type: Option<String>,
    pub long_name: Option<String>,
    pub predefined_type: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GroupMembership {
    pub relationship_id: u32,
    pub group_id: u32,
    pub object_id: u32,
    pub factor: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProductAssignment {
    pub relationship_id: u32,
    pub product_id: u32,
    pub object_id: u32,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct ConnectionsData {
    pub element_connections: Vec<ElementConnection>,
    pub connections_by_element: BTreeMap<u32, Vec<u32>>,
    pub ports: BTreeMap<u32, PortDefinition>,
    pub port_to_element: Vec<PortToElementConnection>,
    pub ports_by_element: BTreeMap<u32, Vec<u32>>,
    pub elements_by_port: BTreeMap<u32, Vec<u32>>,
    pub port_connections: Vec<PortConnection>,
    pub connected_ports: BTreeMap<u32, Vec<u32>>,
    pub space_boundaries: Vec<SpaceBoundary>,
    pub boundaries_by_space: BTreeMap<u32, Vec<u32>>,
    pub boundaries_by_element: BTreeMap<u32, Vec<u32>>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PortDefinition {
    pub express_id: u32,
    pub ifc_type: String,
    pub global_id: Option<String>,
    pub name: Option<String>,
    pub description: Option<String>,
    pub object_type: Option<String>,
    pub flow_direction: Option<String>,
    pub predefined_type: Option<String>,
    pub system_type: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ElementConnection {
    pub relationship_id: u32,
    pub relationship_type: String,
    pub relating_element_id: u32,
    pub related_element_id: u32,
    pub connection_geometry_id: Option<u32>,
    pub relating_priorities: Vec<i64>,
    pub related_priorities: Vec<i64>,
    pub relating_connection_type: Option<String>,
    pub related_connection_type: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PortToElementConnection {
    pub relationship_id: u32,
    pub port_id: u32,
    pub element_id: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PortConnection {
    pub relationship_id: u32,
    pub relating_port_id: u32,
    pub related_port_id: u32,
    pub realizing_element_id: Option<u32>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SpaceBoundary {
    pub relationship_id: u32,
    pub relationship_type: String,
    pub space_id: u32,
    pub element_id: u32,
    pub connection_geometry_id: Option<u32>,
    pub physical_or_virtual: Option<String>,
    pub internal_or_external: Option<String>,
    pub parent_boundary_id: Option<u32>,
    pub corresponding_boundary_id: Option<u32>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct GeoreferencingData {
    pub has_georeference: bool,
    pub source: Option<String>,
    pub map_conversion: Option<MapConversion>,
    pub projected_crs: Option<ProjectedCrs>,
    pub angle_to_grid_north: Option<f64>,
    pub transform_matrix: Option<[f64; 16]>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MapConversion {
    pub express_id: u32,
    pub ifc_type: String,
    pub source_crs_id: Option<u32>,
    pub target_crs_id: Option<u32>,
    pub eastings: f64,
    pub northings: f64,
    pub orthogonal_height: f64,
    pub x_axis_abscissa: Option<f64>,
    pub x_axis_ordinate: Option<f64>,
    pub scale: Option<f64>,
    pub factor_x: Option<f64>,
    pub factor_y: Option<f64>,
    pub factor_z: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ProjectedCrs {
    pub express_id: u32,
    pub name: String,
    pub description: Option<String>,
    pub geodetic_datum: Option<String>,
    pub vertical_datum: Option<String>,
    pub map_projection: Option<String>,
    pub map_zone: Option<String>,
    pub map_unit_id: Option<u32>,
    pub map_unit: Option<String>,
    pub map_unit_scale: Option<f64>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct SpatialData {
    pub project_id: Option<u32>,
    pub roots: Vec<SpatialNode>,
    pub orphan_spatial_ids: Vec<u32>,
    pub by_storey: BTreeMap<u32, Vec<u32>>,
    pub by_building: BTreeMap<u32, Vec<u32>>,
    pub by_site: BTreeMap<u32, Vec<u32>>,
    pub by_space: BTreeMap<u32, Vec<u32>>,
    pub storey_elevations: BTreeMap<u32, f64>,
    pub element_to_storey: BTreeMap<u32, u32>,
    pub element_to_container: BTreeMap<u32, u32>,
    pub referenced_by_structure: BTreeMap<u32, Vec<u32>>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpatialNode {
    pub express_id: u32,
    pub ifc_type: String,
    pub global_id: Option<String>,
    pub name: String,
    pub long_name: Option<String>,
    pub elevation: Option<f64>,
    pub children: Vec<SpatialNode>,
    pub elements: Vec<u32>,
    pub referenced_elements: Vec<u32>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct MaterialsData {
    pub associations: Vec<MaterialAssociation>,
    pub definitions: BTreeMap<u32, ResolvedMaterial>,
    pub element_materials: BTreeMap<u32, Vec<ElementMaterialAssignment>>,
    pub property_sets: BTreeMap<u32, ResourcePropertySet>,
    pub properties_by_material: BTreeMap<u32, Vec<u32>>,
    pub properties_by_profile: BTreeMap<u32, Vec<u32>>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ResourcePropertySet {
    pub express_id: u32,
    pub ifc_type: String,
    pub resource_kind: String,
    pub resource_id: Option<u32>,
    pub name: String,
    pub description: Option<String>,
    pub properties: Vec<ifx_entities::PropValue>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MaterialAssociation {
    pub relationship_id: u32,
    pub relating_material_id: u32,
    pub related_objects: Vec<u32>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ElementMaterialAssignment {
    pub definition_id: u32,
    pub inherited_from_type: Option<u32>,
    pub material: ResolvedMaterial,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ResolvedMaterial {
    pub source_definition_id: u32,
    pub resolved_definition_id: u32,
    pub material_type: String,
    pub name: Option<String>,
    pub description: Option<String>,
    pub category: Option<String>,
    pub layers: Vec<MaterialLayer>,
    pub profiles: Vec<MaterialProfile>,
    pub constituents: Vec<MaterialConstituent>,
    pub materials: Vec<MaterialLeaf>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MaterialLayer {
    pub express_id: u32,
    pub material_id: Option<u32>,
    pub material_name: Option<String>,
    pub material_category: Option<String>,
    pub thickness: Option<f64>,
    pub is_ventilated: Option<bool>,
    pub name: Option<String>,
    pub description: Option<String>,
    pub category: Option<String>,
    pub priority: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MaterialProfile {
    pub express_id: u32,
    pub material_id: Option<u32>,
    pub material_name: Option<String>,
    pub material_category: Option<String>,
    pub profile_id: Option<u32>,
    pub name: Option<String>,
    pub description: Option<String>,
    pub category: Option<String>,
    pub priority: Option<f64>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MaterialConstituent {
    pub express_id: u32,
    pub material_id: Option<u32>,
    pub material_name: Option<String>,
    pub material_category: Option<String>,
    pub name: Option<String>,
    pub description: Option<String>,
    pub fraction: Option<f64>,
    pub category: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MaterialLeaf {
    pub express_id: u32,
    pub name: String,
    pub category: Option<String>,
}
