import pandas as pd
x=pd.read_csv('records.csv')
ids=['p_9BPKMPQZJZ','p_TKEVXBC27E','p_TKEVXBC27C','p_2YHYS3GPHP','p_9BPKMPQZJS','p_R7M02REJHG','p_VZGQ9H2GZG','p_2YHYS3GPHA']
print(x[(x.prototype_id.isin(ids)) & (x.kind=='exploratory')][['prototype_id','test','value','record_id','measured_by']].sort_values(['prototype_id','test']).to_string(index=False))
