import pandas as pd
df = pd.read_csv('records.csv')
print(list(df.columns))
h = df[(df.project=='QP-8476') & (df.property=='heat')]
tn6 = h[h.secondary=='TN6'].sort_values('value', ascending=False)
print(tn6[['prototype_id','value']].head(15).to_string())