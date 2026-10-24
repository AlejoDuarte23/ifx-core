from typing import TypedDict

class DerivedUnitElement(TypedDict):
    express_id: int
    unit_id: int
    exponent: int
    symbol: str
    si_scale: float | None

class ResolvedUnit(TypedDict):
    express_id: int
    ifc_type: str
    unit_type: str
    name: str
    symbol: str
    si_scale: float | None
    conversion_offset: float | None
    elements: list[DerivedUnitElement]

class UnitsData(TypedDict):
    assignment_id: int | None
    by_type: dict[str, ResolvedUnit]

class RelationshipEdge(TypedDict):
    relationship_id: int
    relationship_type: str
    relating_id: int
    related_id: int

class RelationshipData(TypedDict):
    edges: list[RelationshipEdge]

class VoidRelationship(TypedDict):
    relationship_id: int
    element_id: int
    opening_id: int

class FillRelationship(TypedDict):
    relationship_id: int
    opening_id: int
    filling_id: int

class OpeningsData(TypedDict):
    voids: list[VoidRelationship]
    fills: list[FillRelationship]
    openings_by_element: dict[int, list[int]]
    elements_by_opening: dict[int, list[int]]
    fillings_by_opening: dict[int, list[int]]
    openings_by_filling: dict[int, list[int]]

class ClassificationSystem(TypedDict):
    express_id: int
    source: str | None
    edition: str | None
    edition_date: str | None
    name: str
    description: str | None
    location: str | None
    reference_tokens: list[str]

class ClassificationReference(TypedDict):
    express_id: int
    location: str | None
    identification: str | None
    name: str | None
    referenced_source_id: int | None
    description: str | None
    sort: str | None
    system_id: int | None
    system_name: str | None
    path: list[str]

class ClassificationAssociation(TypedDict):
    relationship_id: int
    classification_id: int
    related_objects: list[int]

class ElementClassificationAssignment(TypedDict):
    classification_id: int
    inherited_from_type: int | None

class ClassificationsData(TypedDict):
    systems: dict[int, ClassificationSystem]
    references: dict[int, ClassificationReference]
    associations: list[ClassificationAssociation]
    element_classifications: dict[int, list[ElementClassificationAssignment]]

class DocumentDefinition(TypedDict):
    express_id: int
    document_type: str
    referenced_document_id: int | None
    identification: str | None
    name: str | None
    description: str | None
    location: str | None
    purpose: str | None
    intended_use: str | None
    scope: str | None
    revision: str | None
    electronic_format: str | None
    valid_from: str | None
    valid_until: str | None
    confidentiality: str | None
    status: str | None

class DocumentAssociation(TypedDict):
    relationship_id: int
    document_id: int
    related_objects: list[int]

class ElementDocumentAssignment(TypedDict):
    definition_id: int
    inherited_from_type: int | None
    document: DocumentDefinition

class DocumentsData(TypedDict):
    definitions: dict[int, DocumentDefinition]
    associations: list[DocumentAssociation]
    element_documents: dict[int, list[ElementDocumentAssignment]]

class GroupDefinition(TypedDict):
    express_id: int
    ifc_type: str
    global_id: str | None
    name: str | None
    description: str | None
    object_type: str | None
    long_name: str | None
    predefined_type: str | None

class GroupMembership(TypedDict):
    relationship_id: int
    group_id: int
    object_id: int
    factor: float | None

class ProductAssignment(TypedDict):
    relationship_id: int
    product_id: int
    object_id: int

class GroupsData(TypedDict):
    definitions: dict[int, GroupDefinition]
    memberships: list[GroupMembership]
    groups_by_object: dict[int, list[GroupMembership]]
    members_by_group: dict[int, list[GroupMembership]]
    product_assignments: list[ProductAssignment]
    products_by_object: dict[int, list[int]]
    objects_by_product: dict[int, list[int]]

class PortDefinition(TypedDict):
    express_id: int
    ifc_type: str
    global_id: str | None
    name: str | None
    description: str | None
    object_type: str | None
    flow_direction: str | None
    predefined_type: str | None
    system_type: str | None

class ElementConnection(TypedDict):
    relationship_id: int
    relationship_type: str
    relating_element_id: int
    related_element_id: int
    connection_geometry_id: int | None
    relating_priorities: list[int]
    related_priorities: list[int]
    relating_connection_type: str | None
    related_connection_type: str | None

class PortToElementConnection(TypedDict):
    relationship_id: int
    port_id: int
    element_id: int

class PortConnection(TypedDict):
    relationship_id: int
    relating_port_id: int
    related_port_id: int
    realizing_element_id: int | None

class SpaceBoundary(TypedDict):
    relationship_id: int
    relationship_type: str
    space_id: int
    element_id: int
    connection_geometry_id: int | None
    physical_or_virtual: str | None
    internal_or_external: str | None
    parent_boundary_id: int | None
    corresponding_boundary_id: int | None

class ConnectionsData(TypedDict):
    element_connections: list[ElementConnection]
    connections_by_element: dict[int, list[int]]
    ports: dict[int, PortDefinition]
    port_to_element: list[PortToElementConnection]
    ports_by_element: dict[int, list[int]]
    elements_by_port: dict[int, list[int]]
    port_connections: list[PortConnection]
    connected_ports: dict[int, list[int]]
    space_boundaries: list[SpaceBoundary]
    boundaries_by_space: dict[int, list[int]]
    boundaries_by_element: dict[int, list[int]]

class MapConversion(TypedDict):
    express_id: int
    ifc_type: str
    source_crs_id: int | None
    target_crs_id: int | None
    eastings: float
    northings: float
    orthogonal_height: float
    x_axis_abscissa: float | None
    x_axis_ordinate: float | None
    scale: float | None
    factor_x: float | None
    factor_y: float | None
    factor_z: float | None

class ProjectedCrs(TypedDict):
    express_id: int
    name: str
    description: str | None
    geodetic_datum: str | None
    vertical_datum: str | None
    map_projection: str | None
    map_zone: str | None
    map_unit_id: int | None
    map_unit: str | None
    map_unit_scale: float | None

class GeoreferencingData(TypedDict):
    has_georeference: bool
    source: str | None
    map_conversion: MapConversion | None
    projected_crs: ProjectedCrs | None
    angle_to_grid_north: float | None
    transform_matrix: list[float] | None

class SpatialNode(TypedDict):
    express_id: int
    ifc_type: str
    global_id: str | None
    name: str
    long_name: str | None
    elevation: float | None
    children: list[SpatialNode]
    elements: list[int]
    referenced_elements: list[int]

class SpatialData(TypedDict):
    project_id: int | None
    roots: list[SpatialNode]
    orphan_spatial_ids: list[int]
    by_storey: dict[int, list[int]]
    by_building: dict[int, list[int]]
    by_site: dict[int, list[int]]
    by_space: dict[int, list[int]]
    storey_elevations: dict[int, float]
    element_to_storey: dict[int, int]
    element_to_container: dict[int, int]
    referenced_by_structure: dict[int, list[int]]

class MaterialAssociation(TypedDict):
    relationship_id: int
    relating_material_id: int
    related_objects: list[int]

class MaterialLayer(TypedDict):
    express_id: int
    material_id: int | None
    material_name: str | None
    material_category: str | None
    thickness: float | None
    is_ventilated: bool | None
    name: str | None
    description: str | None
    category: str | None
    priority: float | None

class MaterialProfile(TypedDict):
    express_id: int
    material_id: int | None
    material_name: str | None
    material_category: str | None
    profile_id: int | None
    name: str | None
    description: str | None
    category: str | None
    priority: float | None

class MaterialConstituent(TypedDict):
    express_id: int
    material_id: int | None
    material_name: str | None
    material_category: str | None
    name: str | None
    description: str | None
    fraction: float | None
    category: str | None

class MaterialLeaf(TypedDict):
    express_id: int
    name: str
    category: str | None

class ResolvedMaterial(TypedDict):
    source_definition_id: int
    resolved_definition_id: int
    material_type: str
    name: str | None
    description: str | None
    category: str | None
    layers: list[MaterialLayer]
    profiles: list[MaterialProfile]
    constituents: list[MaterialConstituent]
    materials: list[MaterialLeaf]

class ElementMaterialAssignment(TypedDict):
    definition_id: int
    inherited_from_type: int | None
    material: ResolvedMaterial

class MaterialsData(TypedDict):
    associations: list[MaterialAssociation]
    definitions: dict[int, ResolvedMaterial]
    element_materials: dict[int, list[ElementMaterialAssignment]]
    property_sets: dict[int, ResourcePropertySet]
    properties_by_material: dict[int, list[int]]
    properties_by_profile: dict[int, list[int]]

class PropertyBase(TypedDict):
    name: str
    value: str
    value_type: str

class PropertyValue(PropertyBase, total=False):
    unit_id: int
    details: dict[str, object]
    issue: str

class ResourcePropertySet(TypedDict):
    express_id: int
    ifc_type: str
    resource_kind: str
    resource_id: int | None
    name: str
    description: str | None
    properties: list[PropertyValue]

class IdExamples(TypedDict):
    count: int
    sample_ids: list[int]
    truncated: bool

class ClassCoverage(TypedDict):
    declared: bool
    is_root: bool
    is_product: bool
    scanned: int
    decoded_for_model_data: int
    exported_rows: int
    mesh_elements: int

class ExtractionCoverage(TypedDict):
    source_products: int
    exported_rows: int
    mesh_elements: int
    represented_products: int
    products_without_metadata: IdExamples
    unmeshed_represented_products: IdExamples
    meshes_without_metadata: IdExamples
    property_issue_occurrences: dict[str, int]

class CoverageReport(TypedDict):
    scan_complete: bool
    total_records: int
    distinct_entity_ids: int
    duplicate_entity_ids: list[int]
    unknown_records: int
    classes: dict[str, ClassCoverage]
    extraction: ExtractionCoverage | None

class ModelData(TypedDict):
    schema: str | None
    entity_count: int
    length_unit_scale: float
    units: UnitsData
    relationships: RelationshipData
    spatial: SpatialData
    openings: OpeningsData
    classifications: ClassificationsData
    documents: DocumentsData
    groups: GroupsData
    connections: ConnectionsData
    georeferencing: GeoreferencingData
    materials: MaterialsData
    coverage: CoverageReport

__version__: str

def model_data(ifc_bytes: bytes) -> ModelData: ...
def model_data_json(ifc_bytes: bytes) -> str: ...

class GeometryElement(TypedDict):
    ifc_type: str
    global_id: str | None
    name: str | None
    color: list[float]
    vertices: bytes
    faces: bytes

class GeometryData(TypedDict):
    up_axis: str
    units: str
    rtc_offset: list[float]
    element_count: int
    elements: dict[int, GeometryElement]

class EntityData(TypedDict):
    length_unit_scale: float
    plane_angle_to_radians: float
    project_id: int | None
    entity_count: int
    entities: dict[int, dict[str, object]]

class Extraction(TypedDict):
    geometry: GeometryData
    entities: EntityData
    model: ModelData

def geometry_data_buffers(ifc_bytes: bytes, quality: str | None = None) -> GeometryData: ...
def geometry_data_json(ifc_bytes: bytes, quality: str | None = None) -> str: ...
def entity_data(
    ifc_bytes: bytes,
    placements: bool = False,
    type_properties: bool = True,
    attributes: bool = True,
) -> EntityData: ...
def extract_ifc(ifc_bytes: bytes, quality: str | None = None) -> Extraction: ...
