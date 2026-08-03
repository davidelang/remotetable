class BackendIds:
    MOCK = "mock"
    GOOGLE_SHEETS = "google-sheets"
    EXCEL_GRAPH = "excel-graph"
    ETHERCALC = "ethercalc"
    BASEROW = "baserow"
    NOCODB = "nocodb"
    POCKETBASE = "pocketbase"
    SUPABASE = "supabase"
    AIRTABLE = "airtable"
    # OnlyOffice/Collabora land later in remotetable (before rclone).
    ONLYOFFICE = "onlyoffice"
    COLLABORA = "collabora"
    ROW_DB = (BASEROW, NOCODB, POCKETBASE, SUPABASE, AIRTABLE)
    LIVE = (GOOGLE_SHEETS, EXCEL_GRAPH, ETHERCALC) + ROW_DB
    ALL = (MOCK,) + LIVE
