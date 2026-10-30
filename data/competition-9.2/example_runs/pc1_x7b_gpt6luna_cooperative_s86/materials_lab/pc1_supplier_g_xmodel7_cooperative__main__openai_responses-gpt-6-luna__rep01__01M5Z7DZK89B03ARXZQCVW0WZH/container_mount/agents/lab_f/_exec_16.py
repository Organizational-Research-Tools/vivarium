import pandas as pd
x=pd.read_csv('records.csv'); print(x.shape);print(x.project.value_counts()); print(x[x.project.str.contains('3617',na=False)].head().to_string())