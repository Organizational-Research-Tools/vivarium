import pandas as pd
x=pd.read_csv('records.csv')
print(x[(x.prototype_id=='p_3KNEMDD3PP')].to_string(index=False))
print('all records')