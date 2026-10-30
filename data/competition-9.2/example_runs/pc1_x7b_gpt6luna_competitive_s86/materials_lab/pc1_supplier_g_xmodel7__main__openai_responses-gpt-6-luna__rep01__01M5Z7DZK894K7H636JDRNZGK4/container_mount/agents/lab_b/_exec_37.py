import pandas as pd
x=pd.read_csv('records.csv')
ids=['p_1R7D8ZYK1G','p_1R7D8ZYK1J','p_1R7D8ZYK1M']
print(x[x.prototype_id.isin(ids)].groupby(['prototype_id','test','kind']).value.agg(['count','mean']).to_string())
print(x[x.prototype_id.isin(ids)&x.test.eq('seal hold temperature')][['prototype_id','kind','value','measured_by']].to_string(index=False))