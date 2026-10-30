import pandas as pd
x=pd.read_csv('records.csv')
print(x[x.prototype_id.str.contains('CD8N0FCX',na=False)].to_string(index=False))
