package org.noise_planet.noisemodelling.wps.NoiseModelling

import geoserver.GeoServer
import geoserver.catalog.Store
import org.geotools.jdbc.JDBCDataStore
import org.h2gis.utilities.wrapper.ConnectionWrapper
import org.slf4j.Logger
import org.slf4j.LoggerFactory

import java.sql.Connection
import java.sql.PreparedStatement

title = 'Import atmospheric settings from COUP-noise CSV'
description = 'Creates an NM5 atmospheric settings table with a REAL ARRAY WINDROSE column.'

inputs = [
        pathFile: [
                name: 'CSV path',
                title: 'CSV path',
                type: String.class
        ],
        tableName: [
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

static List<String> parseCsvLine(String line) {
    List<String> values = []
    StringBuilder currentValue = new StringBuilder()
    boolean inQuotes = false

    for (int index = 0; index < line.length(); index++) {
        char currentChar = line.charAt(index)
        if (currentChar == (char) '"') {
            if (inQuotes && index + 1 < line.length() && line.charAt(index + 1) == (char) '"') {
                currentValue.append('"')
                index++
            } else {
                inQuotes = !inQuotes
            }
        } else if (currentChar == ',' && !inQuotes) {
            values.add(currentValue.toString())
            currentValue = new StringBuilder()
        } else {
            currentValue.append(currentChar)
        }
    }

    values.add(currentValue.toString())
    return values
}

def exec(Connection connection, input) {
    Logger logger = LoggerFactory.getLogger("Atmospheric_Settings_From_Csv")
    connection = new ConnectionWrapper(connection)

    String pathFile = input['pathFile'] as String
    String tableName = (input['tableName'] ?: 'ATMOSPHERIC_SETTINGS').toString().trim().toUpperCase()
    File csvFile = new File(pathFile)
    if (!csvFile.exists()) {
        throw new IllegalArgumentException("Atmospheric settings CSV does not exist: " + pathFile)
    }

    List<String> lines = csvFile.readLines('UTF-8').findAll { line -> line != null && !line.trim().isEmpty() }
    if (lines.size() < 2) {
        throw new IllegalArgumentException("Atmospheric settings CSV must contain a header and at least one row.")
    }

    List<String> headers = parseCsvLine(lines[0]).collect { value -> value.trim().toUpperCase() }
    Map<String, Integer> headerIndex = [:]
    headers.eachWithIndex { String value, int index -> headerIndex[value] = index }

    List<String> requiredHeaders = ['PERIOD', 'TEMPERATURE', 'PRESSURE', 'HUMIDITY', 'GDISC', 'PRIME2520']
    (0..15).each { int index -> requiredHeaders.add("WINDROSE_${index}") }
    requiredHeaders.each { String requiredHeader ->
        if (!headerIndex.containsKey(requiredHeader)) {
            throw new IllegalArgumentException("Atmospheric settings CSV is missing column: " + requiredHeader)
        }
    }

    connection.createStatement().execute("DROP TABLE IF EXISTS " + tableName)
    connection.createStatement().execute(
            "CREATE TABLE " + tableName + " (" +
                    "PERIOD VARCHAR PRIMARY KEY," +
                    "WINDROSE REAL ARRAY," +
                    "PRESSURE REAL," +
                    "HUMIDITY REAL," +
                    "GDISC BOOLEAN," +
                    "PRIME2520 BOOLEAN," +
                    "TEMPERATURE REAL)"
    )

    String insertSql = "INSERT INTO " + tableName +
            " (PERIOD, WINDROSE, PRESSURE, HUMIDITY, GDISC, PRIME2520, TEMPERATURE) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
    PreparedStatement statement = connection.prepareStatement(insertSql)

    lines.drop(1).each { String line ->
        List<String> values = parseCsvLine(line)
        Double[] windrose = new Double[16]
        (0..15).each { int index ->
            windrose[index] = Double.valueOf(values[headerIndex["WINDROSE_${index}"]])
        }

        statement.setString(1, values[headerIndex['PERIOD']].trim().toUpperCase())
        statement.setArray(2, connection.createArrayOf("DOUBLE", windrose))
        statement.setDouble(3, Double.valueOf(values[headerIndex['PRESSURE']]))
        statement.setDouble(4, Double.valueOf(values[headerIndex['HUMIDITY']]))
        statement.setBoolean(5, Boolean.valueOf(values[headerIndex['GDISC']]))
        statement.setBoolean(6, Boolean.valueOf(values[headerIndex['PRIME2520']]))
        statement.setDouble(7, Double.valueOf(values[headerIndex['TEMPERATURE']]))
        statement.addBatch()
    }

    statement.executeBatch()
    statement.close()

    logger.info("Imported atmospheric settings into {}", tableName)
    return tableName
}
