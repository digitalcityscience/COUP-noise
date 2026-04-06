package org.noise_planet.noisemodelling.wps.NoiseModelling

import geoserver.GeoServer
import geoserver.catalog.Store
import groovy.sql.Sql
import org.geotools.jdbc.JDBCDataStore
import org.h2gis.utilities.GeometryTableUtilities
import org.h2gis.utilities.TableLocation
import org.h2gis.utilities.wrapper.ConnectionWrapper
import org.slf4j.Logger
import org.slf4j.LoggerFactory

import java.sql.Connection

title = 'Merge road and railway emission sources into a single source table.'
description = 'Build a unified SOURCES table from LW_ROADS and LW_RAILWAY for propagation and receiver generation.'

inputs = [
        roadTable: [
                name: 'Road emission table name',
                title: 'Road emission table name',
                min: 0, max: 1,
                type: String.class
        ],
        railTable: [
                name: 'Rail emission table name',
                title: 'Rail emission table name',
                min: 0, max: 1,
                type: String.class
        ],
        outputTable: [
                name: 'Output table name',
                title: 'Output table name',
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
    connection = new ConnectionWrapper(connection)
    Sql sql = new Sql(connection)
    Logger logger = LoggerFactory.getLogger("Merge_Transport_Sources")

    String roadTable = (input['roadTable'] ?: '').toString().trim().toUpperCase()
    String railTable = (input['railTable'] ?: '').toString().trim().toUpperCase()
    String outputTable = (input['outputTable'] ?: 'SOURCES').toString().trim().toUpperCase()

    if (roadTable.isEmpty() && railTable.isEmpty()) {
        throw new IllegalArgumentException("At least one of roadTable or railTable must be provided.")
    }

    String referenceTable = roadTable.isEmpty() ? railTable : roadTable
    int srid = GeometryTableUtilities.getSRID(connection, TableLocation.parse(referenceTable))

    List<String> emissionColumns = []
    ['D', 'E', 'N'].each { period ->
        ['63', '125', '250', '500', '1000', '2000', '4000', '8000'].each { frequency ->
            emissionColumns.add("HZ${period}${frequency}")
        }
    }

    String columnDefinitions = emissionColumns.collect { "${it} DOUBLE PRECISION" }.join(", ")
    List<String> insertColumns = ['PK', 'IDSOURCE', 'THE_GEOM', 'DIR_ID'] + emissionColumns
    String insertColumnList = insertColumns.join(", ")
    String roadEmissionList = emissionColumns.join(", ")
    String railEmissionList = emissionColumns.join(", ")

    sql.execute("DROP TABLE IF EXISTS " + outputTable)
    sql.execute(
            "CREATE TABLE " + outputTable +
                    "(PK INTEGER NOT NULL, IDSOURCE INTEGER, THE_GEOM GEOMETRY, DIR_ID INTEGER, " +
                    columnDefinitions + ")"
    )

    if (!roadTable.isEmpty()) {
        sql.execute(
                "INSERT INTO " + outputTable + " (" + insertColumnList + ") " +
                        "SELECT PK, COALESCE(IDSOURCE, PK), ST_UPDATEZ(THE_GEOM, 0.05), CAST(NULL AS INTEGER), " +
                        roadEmissionList + " FROM " + roadTable
        )
    }

    if (!railTable.isEmpty()) {
        Number maxPkRow = sql.firstRow("SELECT COALESCE(MAX(PK), 0) AS MAX_PK FROM " + outputTable)?.MAX_PK as Number
        long maxPk = maxPkRow == null ? 0L : maxPkRow.longValue()
        sql.execute(
                "INSERT INTO " + outputTable + " (" + insertColumnList + ") " +
                        "SELECT CAST(ROW_NUMBER() OVER (ORDER BY PK_SECTION, COALESCE(DIR_ID, 0)) + " + maxPk + " AS INTEGER), " +
                        "PK_SECTION, ST_UPDATEZ(THE_GEOM, 0.05), DIR_ID, " +
                        railEmissionList + " FROM " + railTable
        )
    }

    sql.execute("ALTER TABLE " + outputTable + " ADD PRIMARY KEY (PK)")
    sql.execute("CREATE SPATIAL INDEX ON " + outputTable + "(THE_GEOM)")
    sql.execute("CREATE INDEX ON " + outputTable + "(IDSOURCE)")
    sql.execute(String.format("SELECT UpdateGeometrySRID('%s','THE_GEOM',%d)", outputTable, srid))

    logger.info("Merged transport sources into {}", outputTable)
    return outputTable
}
