class BackendIds:
    MOCK = "mock"
    GOOGLE_SHEETS = "google-sheets"
    EXCEL_GRAPH = "excel-graph"
    ETHERCALC = "ethercalc"
    LIVE = (GOOGLE_SHEETS, EXCEL_GRAPH, ETHERCALC)
    ALL = (MOCK,) + LIVE
