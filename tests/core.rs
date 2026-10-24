use ifx_core::{analyze_ifc, Error};

fn wrap(body: &str) -> Vec<u8> {
    wrap_schema("IFC4", body)
}

fn wrap_schema(schema: &str, body: &str) -> Vec<u8> {
    format!(
        "ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('{}'));\nENDSEC;\nDATA;\n{}\nENDSEC;\nEND-ISO-10303-21;",
        schema, body
    )
    .into_bytes()
}

#[test]
fn accepts_supported_schema_releases() {
    let body = "#1=IFCPROJECT('P',$,'Project',$,$,$,$,$,$);";

    assert_eq!(
        analyze_ifc(&wrap_schema("IFC4", body))
            .unwrap()
            .schema
            .as_deref(),
        Some("IFC4")
    );
    assert_eq!(
        analyze_ifc(&wrap_schema("IFC4X3_ADD2", body))
            .unwrap()
            .schema
            .as_deref(),
        Some("IFC4X3")
    );

    assert_eq!(
        analyze_ifc(&wrap_schema("IFC2X3", body))
            .unwrap()
            .schema
            .as_deref(),
        Some("IFC2X3")
    );
    for schema in ["IFC5", "IFC4X3_FAKE", "IFC2X3_UNKNOWN"] {
        let error = analyze_ifc(&wrap_schema(schema, body)).unwrap_err();
        assert!(matches!(error, Error::InvalidIfc(_)));
        assert!(error
            .to_string()
            .contains("unsupported or missing IFC schema"));
    }
}

#[test]
fn rejects_missing_entities_and_missing_project() {
    let no_entities = wrap("");
    assert!(matches!(
        analyze_ifc(&no_entities),
        Err(Error::InvalidIfc(message)) if message.contains("no STEP entities")
    ));

    let no_project = wrap("#1=IFCWALL();");
    assert!(matches!(
        analyze_ifc(&no_project),
        Err(Error::InvalidIfc(message)) if message.contains("no IfcProject")
    ));
}

#[test]
fn system_services_skip_unset_endpoints() {
    for schema in ["IFC2X3", "IFC4", "IFC4X3_ADD2"] {
        let source = wrap_schema(
            schema,
            r#"
#1=IFCPROJECT('P',$,'Project',$,$,$,$,$,$);
#10=IFCBUILDING('B',$,'Building',$,$,$,$,$,.ELEMENT.,$,$,$);
#20=IFCSYSTEM('S',$,'Ventilation',$,$);
#30=IFCRELSERVICESBUILDINGS('R1',$,$,$,$,(#10));
#31=IFCRELSERVICESBUILDINGS('R2',$,$,$,#20,$);
#32=IFCRELSERVICESBUILDINGS('R3',$,$,$,.NULL.,(#10));
#33=IFCRELSERVICESBUILDINGS('R4',$,$,$,#20,($));
"#,
        );
        let model = analyze_ifc(&source).unwrap();
        assert!(model.relationships.edges.is_empty(), "{schema}");
    }
}

#[test]
fn resolves_conversion_based_length_units() {
    let ifc = wrap(
        r#"
#1=IFCPROJECT('P',$,'Project',$,$,$,$,$,#2);
#2=IFCUNITASSIGNMENT((#22));
#19=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#20=IFCDIMENSIONALEXPONENTS(1,0,0,0,0,0,0);
#21=IFCMEASUREWITHUNIT(IFCLENGTHMEASURE(0.3048),#19);
#22=IFCCONVERSIONBASEDUNIT(#20,.LENGTHUNIT.,'FOOT',#21);
"#,
    );

    let data = analyze_ifc(&ifc).expect("conversion-based units should parse");
    assert!((data.length_unit_scale - 0.3048).abs() < f64::EPSILON);
}

#[test]
fn resolves_project_units_with_symbols_scales_offsets_and_derived_elements() {
    let ifc = wrap(
        r#"
#1=IFCPROJECT('P',$,'Project',$,$,$,$,$,#2);
#2=IFCUNITASSIGNMENT((#3,#4,#8,#13,#14,#15,#19));
#3=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#4=IFCSIUNIT(*,.AREAUNIT.,.MILLI.,.SQUARE_METRE.);
#5=IFCSIUNIT(*,.PLANEANGLEUNIT.,$,.RADIAN.);
#6=IFCDIMENSIONALEXPONENTS(0,0,0,0,0,0,0);
#7=IFCMEASUREWITHUNIT(IFCPLANEANGLEMEASURE(0.0174532925199433),#5);
#8=IFCCONVERSIONBASEDUNIT(#6,.PLANEANGLEUNIT.,'DEGREE',#7);
#9=IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.);
#10=IFCSIUNIT(*,.TIMEUNIT.,$,.SECOND.);
#11=IFCDERIVEDUNITELEMENT(#9,1);
#12=IFCDERIVEDUNITELEMENT(#10,-1);
#13=IFCDERIVEDUNIT((#11,#12),.VOLUMETRICFLOWRATEUNIT.,$);
#14=IFCMONETARYUNIT('USD');
#15=IFCCONTEXTDEPENDENTUNIT(#6,.USERDEFINED.,'widget');
#16=IFCSIUNIT(*,.THERMODYNAMICTEMPERATUREUNIT.,$,.KELVIN.);
#17=IFCMEASUREWITHUNIT(IFCTHERMODYNAMICTEMPERATUREMEASURE(0.555555555555556),#16);
#19=IFCCONVERSIONBASEDUNITWITHOFFSET(#6,.THERMODYNAMICTEMPERATUREUNIT.,'FAHRENHEIT',#17,459.67);
"#,
    );

    let data = analyze_ifc(&ifc).expect("project units should parse");
    assert_eq!(data.units.assignment_id, Some(2));
    assert_eq!(data.units.by_type["LENGTHUNIT"].symbol, "mm");
    assert_eq!(data.units.by_type["LENGTHUNIT"].si_scale, Some(0.001));
    assert_eq!(data.units.by_type["AREAUNIT"].symbol, "mm²");
    assert_eq!(data.units.by_type["AREAUNIT"].si_scale, Some(1e-6));
    let angle = &data.units.by_type["PLANEANGLEUNIT"];
    assert_eq!(angle.symbol, "°");
    assert!((angle.si_scale.unwrap() - std::f64::consts::PI / 180.0).abs() < 1e-14);
    let flow = &data.units.by_type["VOLUMETRICFLOWRATEUNIT"];
    assert_eq!(flow.symbol, "m³/s");
    assert_eq!(flow.si_scale, Some(1.0));
    assert_eq!(flow.elements.len(), 2);
    assert_eq!(flow.elements[1].exponent, -1);
    assert_eq!(data.units.by_type["MONETARYUNIT"].symbol, "$");
    assert_eq!(data.units.by_type["USERDEFINED"].si_scale, None);
    let temperature = &data.units.by_type["THERMODYNAMICTEMPERATUREUNIT"];
    assert_eq!(temperature.ifc_type, "IfcConversionBasedUnitWithOffset");
    assert_eq!(temperature.conversion_offset, Some(459.67));
}

#[test]
fn resolves_openings_fillings_and_spatial_ancestry() {
    let ifc = wrap(
        r#"
#1=IFCPROJECT('P',$,'Project',$,$,$,$,$,$);
#10=IFCBUILDINGSTOREY('S',$,'Level 1',$,$,$,$,$,.ELEMENT.,0.);
#100=IFCWALL('W',$,'Wall',$,$,$,$,$,$);
#101=IFCOPENINGELEMENT('O1',$,'Door opening',$,$,$,$,$,$);
#102=IFCDOOR('D',$,'Door',$,$,$,$,$,2.,1.,$,$,$,$);
#103=IFCOPENINGELEMENT('O2',$,'Window opening',$,$,$,$,$,$);
#104=IFCWINDOW('WIN',$,'Window',$,$,$,$,$,1.,1.,$,$,$);
#200=IFCRELAGGREGATES('A',$,$,$,#1,(#10));
#201=IFCRELCONTAINEDINSPATIALSTRUCTURE('C',$,$,$,(#100),#10);
#202=IFCRELVOIDSELEMENT('V1',$,$,$,#100,#101);
#203=IFCRELFILLSELEMENT('F1',$,$,$,#101,#102);
#204=IFCRELVOIDSELEMENT('V2',$,$,$,#100,#103);
#205=IFCRELFILLSELEMENT('F2',$,$,$,#103,#104);
"#,
    );

    let data = analyze_ifc(&ifc).expect("opening relationships should parse");
    assert_eq!(
        data,
        analyze_ifc(&ifc).expect("repeated opening extraction should parse")
    );
    assert_eq!(data.openings.voids.len(), 2);
    assert_eq!(data.openings.fills.len(), 2);
    assert_eq!(data.openings.openings_by_element[&100], vec![101, 103]);
    assert_eq!(data.openings.elements_by_opening[&101], vec![100]);
    assert_eq!(data.openings.fillings_by_opening[&101], vec![102]);
    assert_eq!(data.openings.openings_by_filling[&104], vec![103]);
    for express_id in [100, 101, 102, 103, 104] {
        assert_eq!(data.spatial.element_to_container[&express_id], 10);
        assert_eq!(data.spatial.element_to_storey[&express_id], 10);
    }
    let edge_types: Vec<&str> = data
        .relationships
        .edges
        .iter()
        .filter(|edge| edge.relationship_id >= 202)
        .map(|edge| edge.relationship_type.as_str())
        .collect();
    assert_eq!(
        edge_types,
        vec![
            "IfcRelVoidsElement",
            "IfcRelFillsElement",
            "IfcRelVoidsElement",
            "IfcRelFillsElement",
        ]
    );
}

#[test]
fn extracts_ifclite_relationship_graph_directions() {
    let ifc = wrap(
        r#"
#1=IFCPROJECT('P',$,'Project',$,$,$,$,$,$);
#200=IFCRELDEFINESBYPROPERTIES('P',$,$,$,(#10,#11),(#20,#21));
#201=IFCRELASSOCIATESCLASSIFICATION('C',$,$,$,(#10,#11),#30);
#202=IFCRELASSOCIATESDOCUMENT('D',$,$,$,(#10),#31);
#203=IFCRELASSIGNSTOGROUP('G',$,$,$,(#10,#11),$,#40);
#204=IFCRELASSIGNSTOGROUPBYFACTOR('GF',$,$,$,(#12),$,#40,0.5);
#205=IFCRELASSIGNSTOPRODUCT('P',$,$,$,(#10,#11),$,#41);
#206=IFCRELCONNECTSELEMENTS('CE',$,$,$,$,#10,#11);
#207=IFCRELCONNECTSPATHELEMENTS('CP',$,$,$,$,#11,#12,(),(),.ATSTART.,.ATEND.);
#208=IFCRELCONNECTSPORTTOELEMENT('PE',$,$,$,#50,#10);
#209=IFCRELCONNECTSPORTS('PP',$,$,$,#50,#51,$);
#210=IFCRELSPACEBOUNDARY('SB',$,$,$,#60,#10,$,.PHYSICAL.,.INTERNAL.);
"#,
    );

    let data = analyze_ifc(&ifc).expect("relationship graph should parse");
    let edges: Vec<(&str, u32, u32)> = data
        .relationships
        .edges
        .iter()
        .map(|edge| {
            (
                edge.relationship_type.as_str(),
                edge.relating_id,
                edge.related_id,
            )
        })
        .collect();
    assert_eq!(
        edges,
        vec![
            ("IfcRelDefinesByProperties", 20, 10),
            ("IfcRelDefinesByProperties", 20, 11),
            ("IfcRelDefinesByProperties", 21, 10),
            ("IfcRelDefinesByProperties", 21, 11),
            ("IfcRelAssociatesClassification", 30, 10),
            ("IfcRelAssociatesClassification", 30, 11),
            ("IfcRelAssociatesDocument", 31, 10),
            ("IfcRelAssignsToGroup", 40, 10),
            ("IfcRelAssignsToGroup", 40, 11),
            ("IfcRelAssignsToGroupByFactor", 40, 12),
            ("IfcRelAssignsToProduct", 41, 10),
            ("IfcRelAssignsToProduct", 41, 11),
            ("IfcRelConnectsElements", 10, 11),
            ("IfcRelConnectsPathElements", 11, 12),
            ("IfcRelConnectsPortToElement", 50, 10),
            ("IfcRelConnectsPorts", 50, 51),
            ("IfcRelSpaceBoundary", 60, 10),
        ]
    );
}

#[test]
fn spatial_cycles_terminate_and_are_deterministic() {
    let ifc = wrap(
        r#"
#1=IFCPROJECT('P',$,'Project',$,$,$,$,$,$);
#10=IFCSITE('S',$,'Site',$,$,$,$,$,.ELEMENT.,$,$,$,$,$);
#11=IFCBUILDING('B',$,'Building',$,$,$,$,$,.ELEMENT.,$,$,$);
#100=IFCWALL();
#110=IFCRELAGGREGATES('R1',$,$,$,#1,(#10));
#111=IFCRELAGGREGATES('R2',$,$,$,#10,(#11));
#112=IFCRELAGGREGATES('R3',$,$,$,#11,(#10));
#113=IFCRELCONTAINEDINSPATIALSTRUCTURE('R4',$,$,$,(#100),#11);
#114=IFCRELAGGREGATES('R5',$,$,$,#100,(#100));
"#,
    );

    let first = analyze_ifc(&ifc).expect("cycles must be guarded");
    let second = analyze_ifc(&ifc).expect("the same model must remain parseable");
    assert_eq!(first, second);
    assert_eq!(first.spatial.element_to_container.get(&100), Some(&11));
    assert_eq!(
        first.spatial.roots[0].children[0].children[0]
            .children
            .len(),
        1
    );
    assert!(first.spatial.roots[0].children[0].children[0].children[0]
        .children
        .is_empty());
}

#[test]
fn unresolved_material_references_are_preserved_as_edges_without_panicking() {
    let ifc = wrap(
        r#"
#1=IFCPROJECT('P',$,'Project',$,$,$,$,$,$);
#10=IFCWALL();
#20=IFCRELASSOCIATESMATERIAL('M',$,$,$,(#10),#999);
"#,
    );

    let data = analyze_ifc(&ifc).expect("a dangling reference is recoverable");
    assert_eq!(data.relationships.edges.len(), 1);
    assert_eq!(data.materials.associations[0].relating_material_id, 999);
    assert!(data.materials.element_materials.is_empty());
}

#[test]
fn builds_ifclite_compatible_spatial_hierarchy_and_reverse_maps() {
    let ifc = wrap(
        r#"
#1=IFCPROJECT('P',$,'Project',$,$,$,$,$,#2);
#2=IFCUNITASSIGNMENT((#3));
#3=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#10=IFCSITE('S',$,'Site',$,$,$,$,'Campus',.ELEMENT.,$,$,$,$,$);
#11=IFCBUILDING('B',$,'Building',$,$,$,$,'HQ',.ELEMENT.,$,$,$);
#12=IFCBUILDINGSTOREY('ST',$,'Level 1',$,$,#20,$,'First floor',.ELEMENT.,$);
#13=IFCSPACE('SP',$,'101',$,$,$,$,'Room',.ELEMENT.,.INTERNAL.);
#20=IFCLOCALPLACEMENT($,#21);
#21=IFCAXIS2PLACEMENT3D(#22,$,$);
#22=IFCCARTESIANPOINT((0.,0.,3000.));
#100=IFCWALL();
#101=IFCGRID();
#102=IFCBUILDINGELEMENTPART();
#103=IFCFURNISHINGELEMENT();
#104=IFCDISTRIBUTIONELEMENT();
#110=IFCRELAGGREGATES('R1',$,$,$,#1,(#10));
#111=IFCRELAGGREGATES('R2',$,$,$,#10,(#11));
#112=IFCRELAGGREGATES('R3',$,$,$,#11,(#12));
#113=IFCRELAGGREGATES('R4',$,$,$,#12,(#13));
#114=IFCRELCONTAINEDINSPATIALSTRUCTURE('R5',$,$,$,(#13,#100,#101),#12);
#115=IFCRELCONTAINEDINSPATIALSTRUCTURE('R6',$,$,$,(#103),#13);
#116=IFCRELAGGREGATES('R7',$,$,$,#100,(#102));
#117=IFCRELNESTS('R8',$,$,$,#100,(#104));
#118=IFCRELREFERENCEDINSPATIALSTRUCTURE('R9',$,$,$,(#103),#12);
"#,
    );

    let data = analyze_ifc(&ifc).expect("synthetic IFC should parse");
    assert_eq!(data.schema.as_deref(), Some("IFC4"));
    assert_eq!(data.length_unit_scale, 0.001);
    assert_eq!(data.spatial.project_id, Some(1));
    assert_eq!(data.spatial.roots.len(), 1);
    assert_eq!(data.spatial.by_storey.get(&12), Some(&vec![100, 101]));
    assert_eq!(data.spatial.by_space.get(&13), Some(&vec![103]));
    assert_eq!(data.spatial.storey_elevations.get(&12), Some(&3.0));
    assert_eq!(data.spatial.element_to_storey.get(&13), Some(&12));
    assert_eq!(data.spatial.element_to_storey.get(&102), Some(&12));
    assert_eq!(data.spatial.element_to_storey.get(&104), Some(&12));
    assert_eq!(data.spatial.element_to_container.get(&103), Some(&13));
    assert_eq!(
        data.spatial.referenced_by_structure.get(&12),
        Some(&vec![103])
    );

    let storey = &data.spatial.roots[0].children[0].children[0].children[0];
    assert_eq!(storey.express_id, 12);
    assert_eq!(storey.children.len(), 1, "space must be deduplicated");
    assert_eq!(storey.children[0].express_id, 13);
    assert_eq!(storey.elevation, Some(3.0));
}

#[test]
fn resolves_material_families_precedence_and_deterministic_order() {
    let ifc = wrap(
        r#"
#1=IFCPROJECT('P',$,'Project',$,$,$,$,$,#2);
#2=IFCUNITASSIGNMENT((#3));
#3=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#100=IFCWALL();
#101=IFCWALL();
#102=IFCWALL();
#103=IFCWALL();
#104=IFCWALL();
#105=IFCBEAM();
#106=IFCWALL();
#500=IFCWALLTYPE();
#200=IFCMATERIAL('Concrete','Structural concrete','Concrete');
#201=IFCMATERIAL('Insulation',$,'Thermal');
#202=IFCMATERIAL('Steel',$,'Metal');
#210=IFCMATERIALCONSTITUENTSET('Composite',$,(#211,#212));
#211=IFCMATERIALCONSTITUENT('Core',$,#200,0.75,'Core');
#212=IFCMATERIALCONSTITUENT('Finish',$,#201,0.25,'Finish');
#220=IFCMATERIALLAYERSETUSAGE(#221,.AXIS2.,.POSITIVE.,0.,$);
#221=IFCMATERIALLAYERSET((#222,#223),'Wall build-up',$);
#222=IFCMATERIALLAYER(#200,200.,.F.,'Core',$,'Structure',$);
#223=IFCMATERIALLAYER(#201,50.,.T.,'Insulation',$,'Thermal',$);
#230=IFCMATERIALPROFILESET('Beam set',$,(#231),$);
#231=IFCMATERIALPROFILE('Steel profile',$,#202,$,$,'Structure');
#240=IFCMATERIALLIST((#200,#202));
#300=IFCRELASSOCIATESMATERIAL('M1',$,$,$,(#100),#210);
#301=IFCRELASSOCIATESMATERIAL('M2',$,$,$,(#500),#201);
#302=IFCRELDEFINESBYTYPE('T1',$,$,$,(#101,#102),#500);
#303=IFCRELASSOCIATESMATERIAL('M3',$,$,$,(#102),#202);
#304=IFCRELASSOCIATESMATERIAL('M4',$,$,$,(#104),#220);
#305=IFCRELASSOCIATESMATERIAL('M5',$,$,$,(#105),#230);
#306=IFCRELASSOCIATESMATERIAL('M6',$,$,$,(#106),#240);
#900=IFCRELASSOCIATESMATERIAL('M9',$,$,$,(#103),#200);
#800=IFCRELASSOCIATESMATERIAL('M8',$,$,$,(#103),#202);
#1000=IFCRELASSOCIATESMATERIAL('M10',$,$,$,(#103),#202);
"#,
    );

    let data = analyze_ifc(&ifc).expect("synthetic IFC should parse");
    let materials = data.materials;

    let wall_100 = &materials.element_materials[&100][0];
    assert_eq!(wall_100.material.material_type, "MaterialConstituentSet");
    assert_eq!(wall_100.material.constituents.len(), 2);
    assert_eq!(
        wall_100.material.constituents[0].material_name.as_deref(),
        Some("Concrete")
    );

    let inherited = &materials.element_materials[&101][0];
    assert_eq!(inherited.definition_id, 201);
    assert_eq!(inherited.inherited_from_type, Some(500));
    assert_eq!(inherited.material.name.as_deref(), Some("Insulation"));

    let overridden = &materials.element_materials[&102];
    assert_eq!(overridden.len(), 1);
    assert_eq!(overridden[0].definition_id, 202);
    assert_eq!(overridden[0].inherited_from_type, None);

    let multiple: Vec<u32> = materials.element_materials[&103]
        .iter()
        .map(|assignment| assignment.definition_id)
        .collect();
    assert_eq!(
        multiple,
        vec![202, 200],
        "lowest relationship ID wins ordering"
    );

    let layers = &materials.element_materials[&104][0].material;
    assert_eq!(layers.source_definition_id, 220);
    assert_eq!(layers.resolved_definition_id, 221);
    assert_eq!(layers.layers[0].thickness, Some(0.2));
    assert_eq!(layers.layers[1].thickness, Some(0.05));

    assert_eq!(
        materials.element_materials[&105][0].material.profiles.len(),
        1
    );
    assert_eq!(
        materials.element_materials[&106][0]
            .material
            .materials
            .len(),
        2
    );
    assert!(
        !materials.element_materials.contains_key(&500),
        "type objects are definitions, not elements"
    );
    assert!(materials.definitions.contains_key(&200));
    assert!(materials.definitions.contains_key(&210));
    assert!(materials.definitions.contains_key(&220));
}

#[test]
fn semantic_expansion_is_typed_and_deterministic() {
    let ifc = wrap(
        r#"
#1=IFCPROJECT('P',$,'Project',$,$,$,$,$,#2);
#2=IFCUNITASSIGNMENT((#3));
#3=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#10=IFCWALL('W',$,'Wall',$,$,$,$,$,$);
#11=IFCWALLTYPE('WT',$,'Wall type',$,$,$,$,$,$,$);
#12=IFCWALL('W2',$,'Wall 2',$,$,$,$,$,$);
#20=IFCCLASSIFICATION('NBS','2025','2025-01-01','Uniclass','System','https://example.test',('Pr'));
#21=IFCCLASSIFICATIONREFERENCE($,'Pr_20','Products',#20,$,$);
#22=IFCCLASSIFICATIONREFERENCE($,'Pr_20_93','Unit products',#21,$,$);
#30=IFCDOCUMENTINFORMATION('DOC-1','Manual','Canonical','manual.pdf','Install','Construction','Project','B',$,$,$,$,'application/pdf','2025-01-01','2030-01-01',.PUBLIC.,.FINAL.);
#31=IFCDOCUMENTREFERENCE('local.pdf',$,$,'Reference description',#30);
#40=IFCGROUP('G',$,'Review group','Review members','Review set');
#50=IFCDISTRIBUTIONPORT('PA',$,'Port A',$,$,$,$,.SOURCE.,.PIPE.,.WATERSUPPLY.);
#51=IFCDISTRIBUTIONPORT('PB',$,'Port B',$,$,$,$,.SINK.,.PIPE.,.WATERSUPPLY.);
#60=IFCSPACE('S',$,'Room',$,$,$,$,$,.ELEMENT.,.INTERNAL.);
#70=IFCPROJECTEDCRS('EPSG:28992','RD New','Amersfoort','NAP','Stereographic','NL',#3);
#71=IFCMAPCONVERSION(#72,#70,155000.,463000.,1.5,0.,1.,0.9999);
#200=IFCRELDEFINESBYTYPE('T',$,$,$,(#10),#11);
#201=IFCRELASSOCIATESCLASSIFICATION('C',$,$,$,(#11),#22);
#202=IFCRELASSOCIATESDOCUMENT('D',$,$,$,(#10),#31);
#203=IFCRELASSIGNSTOGROUPBYFACTOR('G',$,$,$,(#10),$,#40,0.25);
#204=IFCRELCONNECTSPATHELEMENTS('P',$,$,$,$,#10,#12,(10,20),(30),.ATEND.,.ATSTART.);
#205=IFCRELCONNECTSPORTTOELEMENT('PE1',$,$,$,#50,#10);
#206=IFCRELCONNECTSPORTTOELEMENT('PE2',$,$,$,#51,#12);
#207=IFCRELCONNECTSPORTS('PP',$,$,$,#50,#51,#10);
#208=IFCRELSPACEBOUNDARY2NDLEVEL('SB',$,$,$,#60,#10,$,.PHYSICAL.,.INTERNAL.,$,$);
"#,
    );

    let first = analyze_ifc(&ifc).expect("expanded semantic data should parse");
    let second = analyze_ifc(&ifc).expect("repeated extraction should parse");
    assert_eq!(first, second);

    assert_eq!(first.classifications.references[&22].system_id, Some(20));
    assert_eq!(
        first.classifications.references[&22].path,
        vec!["Pr_20", "Pr_20_93"]
    );
    let inherited = &first.classifications.element_classifications[&10][0];
    assert_eq!(inherited.classification_id, 22);
    assert_eq!(inherited.inherited_from_type, Some(11));

    let document = &first.documents.element_documents[&10][0].document;
    assert_eq!(document.identification.as_deref(), Some("DOC-1"));
    assert_eq!(document.name.as_deref(), Some("Manual"));
    assert_eq!(
        document.description.as_deref(),
        Some("Reference description")
    );
    assert_eq!(document.status.as_deref(), Some("FINAL"));

    assert_eq!(first.groups.groups_by_object[&10][0].group_id, 40);
    assert_eq!(first.groups.groups_by_object[&10][0].factor, Some(0.25));
    assert_eq!(
        first.connections.element_connections[0].relating_priorities,
        vec![10, 20]
    );
    assert_eq!(
        first.connections.element_connections[0]
            .relating_connection_type
            .as_deref(),
        Some("ATSTART")
    );
    assert_eq!(first.connections.ports_by_element[&10], vec![50]);
    assert_eq!(first.connections.connected_ports[&50], vec![51]);
    assert_eq!(first.connections.space_boundaries[0].relationship_id, 208);

    assert!(first.georeferencing.has_georeference);
    assert_eq!(
        first.georeferencing.source.as_deref(),
        Some("mapConversion")
    );
    assert_eq!(
        first
            .georeferencing
            .projected_crs
            .as_ref()
            .unwrap()
            .map_unit_scale,
        Some(0.001)
    );
    assert!((first.georeferencing.angle_to_grid_north.unwrap() - 90.0).abs() < 1e-12);
    assert_eq!(first.georeferencing.transform_matrix.unwrap()[12], 155000.0);
}
