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
    FIREBASE = "firebase"
    ZOHO_SHEET = "zoho-sheet"
    ONLYOFFICE = "onlyoffice"
    COLLABORA = "collabora"
    ROW_DB = (BASEROW, NOCODB, POCKETBASE, SUPABASE, AIRTABLE, FIREBASE)
    LIVE = (GOOGLE_SHEETS, EXCEL_GRAPH, ETHERCALC, ZOHO_SHEET) + ROW_DB
    ALL = (MOCK,) + LIVE + (ONLYOFFICE, COLLABORA)
