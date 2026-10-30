import pandas as pd
x=pd.read_csv('records.csv')
print(x.shape); print(x.columns.tolist()); print(x[x.prototype_id=='p_62M20S6MVN'].to_string(index=False))