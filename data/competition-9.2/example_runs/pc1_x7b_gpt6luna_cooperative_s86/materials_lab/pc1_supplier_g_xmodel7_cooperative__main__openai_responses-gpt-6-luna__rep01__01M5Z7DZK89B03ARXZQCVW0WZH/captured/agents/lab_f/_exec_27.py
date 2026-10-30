import pandas as pd
x=pd.read_csv('records.csv'); p='p_JP6EPY2552'; d=x[x.prototype_id.eq(p)]; print(d.iloc[0,10:].to_dict()); print(d.groupby('test').value.mean())