from databricks import utility

token = "dapi12345678901234567890123456789012"
#dbutils
try:
    utility.fs.ls("/")
except Exception:
    raise 