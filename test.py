from databricks import utility

#dbutils
try:
    utility.fs.ls("/")
except Exception:
    raise 