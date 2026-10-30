import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x[x.prototype_id.eq('p_Y9Y4J1ZWSF')].to_string(index=False))