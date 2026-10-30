import pandas as pd
x=pd.read_csv('records.csv'); print(x[x.prototype_id.eq('p_Z398MDW5ST')].groupby(['test','measured_by','requester']).size())