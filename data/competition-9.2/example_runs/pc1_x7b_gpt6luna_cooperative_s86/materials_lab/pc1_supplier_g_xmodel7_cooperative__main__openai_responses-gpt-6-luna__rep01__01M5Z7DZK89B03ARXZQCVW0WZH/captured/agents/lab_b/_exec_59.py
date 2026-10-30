import pandas as pd
x=pd.read_csv('records.csv')
ids=['p_7FT9YYT843','p_7FT9YYT845','p_7FT9YYT847','p_RKZ9AMQWT8','p_RKZ9AMQWTA']
print(x[x.prototype_id.isin(ids)].groupby(['prototype_id','instrument']).value.agg(['mean','count']).to_string())