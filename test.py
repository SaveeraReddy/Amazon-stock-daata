from databricks import utility

token =  "TEST_DATABRICKS_TOKEN"

try:
    utility.fs.ls("/")
except Exception:
    raise