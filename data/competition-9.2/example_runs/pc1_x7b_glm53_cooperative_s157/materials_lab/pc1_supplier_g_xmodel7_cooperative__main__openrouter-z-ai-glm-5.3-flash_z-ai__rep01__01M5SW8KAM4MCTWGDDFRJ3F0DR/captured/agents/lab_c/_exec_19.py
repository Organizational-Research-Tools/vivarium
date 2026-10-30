import pandas as pd
df=pd.read_csv('records.csv')
prot=sorted(set(df['prototype_id'].dropna()))
known={'p_YM23HABVE7','p_YM23HABVE9','p_94B583XC0W','p_CWYDQP98S8'}
new=[p for p in prot if p not in known]
print(len(new), new)
