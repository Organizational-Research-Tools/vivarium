import pandas as pd
x=pd.read_csv('records.csv'); print(x[(x.project=='QP-6879') & (x.test=='seal hold temperature')].groupby(['prototype_id','measured_by']).value.mean().to_string())