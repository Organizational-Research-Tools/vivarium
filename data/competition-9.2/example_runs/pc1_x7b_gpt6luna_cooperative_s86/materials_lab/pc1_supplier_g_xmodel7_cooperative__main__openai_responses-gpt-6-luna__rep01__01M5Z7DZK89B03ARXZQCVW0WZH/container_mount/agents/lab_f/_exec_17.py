import pandas as pd
x=pd.read_csv('records.csv');q=x[x.project=='QP-3617']; print(q.test.unique());print(q.groupby(['prototype_id','test']).value.mean().to_string())