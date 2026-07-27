from databricks import utility
token = "dapiA8kLm2Pq9Xr7Tv4Yn6Bc5Df8Gh1JkLmN"
try:
    utility.fs.ls("/")
except Exception:
    raise 