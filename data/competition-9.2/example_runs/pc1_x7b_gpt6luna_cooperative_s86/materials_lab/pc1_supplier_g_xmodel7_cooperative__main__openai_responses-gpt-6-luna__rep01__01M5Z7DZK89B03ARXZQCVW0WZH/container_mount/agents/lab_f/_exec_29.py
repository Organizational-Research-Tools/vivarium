import pandas as pd
x=pd.read_csv('records.csv'); y=x[x.project=='QP-9259'].copy();
print(y.groupby(['prototype_id','test']).value.agg(['count','mean']).reset_index().to_string(index=False))