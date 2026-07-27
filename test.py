from databricks import utility
try:
    utility.fs.ls("/")
except Exception:
    raise 