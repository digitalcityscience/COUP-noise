package org.noise_planet.noisemodelling.wps.NoiseModelling

import geoserver.GeoServer
import geoserver.catalog.Store
import groovy.sql.Sql
import org.geotools.jdbc.JDBCDataStore
import org.h2gis.utilities.GeometryMetaData
import org.h2gis.utilities.GeometryTableUtilities
import org.h2gis.utilities.SpatialResultSet
import org.h2gis.utilities.TableLocation
import org.h2gis.utilities.dbtypes.DBUtils
import org.h2gis.utilities.wrapper.ConnectionWrapper
import org.noise_planet.noisemodelling.jdbc.EmissionTableGenerator
import org.slf4j.Logger
import org.slf4j.LoggerFactory

import java.sql.Connection
import java.sql.PreparedStatement
import java.sql.SQLException

title = 'Compute railway emission noise map from vehicle, traffic table and section table.'
description = 'Compute railway emission with the runner-compatible EmissionTableGenerator signature.'

inputs = [
        tableRailwayTraffic: [
                name: 'Railway traffic table name',
                title: 'Railway traffic table name',
                type: String.class
        ],
        tableRailwayTrack: [
                name: 'Railway track table name',
                title: 'Railway track table name',
                type: String.class
        ],
        vehicleDataFile: [
                name: 'Railway vehicle data file',
                title: 'Railway vehicle data file',
                min: 0, max: 1,
                type: String.class
        ],
        trainSetDataFile: [
                name: 'Railway trainset data file',
                title: 'Railway trainset data file',
                min: 0, max: 1,
                type: String.class
        ],
        railwayEmissionDataFile: [
                name: 'Railway emission data file',
                title: 'Railway emission data file',
                min: 0, max: 1,
                type: String.class
        ]
]

outputs = [result: [name: 'Result output string', title: 'Result output string', type: String.class]]

static Connection openGeoserverDataStoreConnection(String dbName) {
    if (dbName == null || dbName.isEmpty()) {
        dbName = new GeoServer().catalog.getStoreNames().get(0)
    }
    Store store = new GeoServer().catalog.getStore(dbName)
    JDBCDataStore jdbcDataStore = (JDBCDataStore) store.getDataStoreInfo().getDataStore(null)
    return jdbcDataStore.getDataSource().getConnection()
}

def run(input) {
    String dbName = "h2gisdb"
    openGeoserverDataStoreConnection(dbName).withCloseable {
        Connection connection ->
            return [result: exec(connection, input)]
    }
}

def exec(Connection connection, input) {
    Logger logger = LoggerFactory.getLogger("Railway_Emission_from_Traffic_Local")
    connection = new ConnectionWrapper(connection)

    String sourcesGeomTableName = (input['tableRailwayTrack'] as String).toUpperCase()
    String sourcesTrafficTableName = (input['tableRailwayTraffic'] as String).toUpperCase()
    String vehicleDataFile = (input['vehicleDataFile'] ?: "RailwayVehiclesCnossos.json") as String
    String trainSetDataFile = (input['trainSetDataFile'] ?: "RailwayTrainsets.json") as String
    String railwayEmissionDataFile = (input['railwayEmissionDataFile'] ?: "RailwayEmissionCnossos.json") as String

    int sridSources = GeometryTableUtilities.getSRID(connection, TableLocation.parse(sourcesGeomTableName))
    if (sridSources == 3785 || sridSources == 4326) {
        throw new IllegalArgumentException("Error : Please use a metric projection for " + sourcesGeomTableName + ".")
    }
    if (sridSources == 0) {
        throw new IllegalArgumentException("Error : The table " + sourcesGeomTableName + " does not have an associated spatial reference system.")
    }

    TableLocation sourceTableIdentifier = TableLocation.parse(sourcesGeomTableName)
    List<String> geomFields = GeometryTableUtilities.getGeometryColumnNames(connection, sourceTableIdentifier)
    if (geomFields.isEmpty()) {
        throw new SQLException(String.format("The table %s does not exists or does not contain a geometry field", sourceTableIdentifier))
    }

    Sql sql = new Sql(connection)
    PreparedStatement statement = connection.prepareStatement("SELECT COUNT(*) AS total FROM " + sourcesGeomTableName)
    SpatialResultSet resultSet = statement.executeQuery().unwrap(SpatialResultSet.class)
    while (resultSet.next()) {
        logger.info("The table {} has {} rail segments.", sourcesGeomTableName, resultSet.getInt("total"))
    }

    EmissionTableGenerator.makeTrainLWTable(
            connection,
            sourcesGeomTableName,
            sourcesTrafficTableName,
            "LW_RAILWAY",
            "HZ",
            vehicleDataFile,
            trainSetDataFile,
            railwayEmissionDataFile
    )

    TableLocation alterTable = TableLocation.parse("LW_RAILWAY", DBUtils.getDBType(connection))
    GeometryMetaData metaData = GeometryTableUtilities.getMetaData(connection, alterTable, "THE_GEOM")
    metaData.setSRID(sridSources)
    sql.execute(
            String.format(
                    "ALTER TABLE %s ALTER COLUMN %s %s USING ST_SetSRID(%s,%d)",
                    alterTable,
                    "THE_GEOM",
                    metaData.getSQL(),
                    "THE_GEOM",
                    metaData.getSRID()
            )
    )

    return "Calculation Done ! The table LW_RAILWAY has been created."
}
