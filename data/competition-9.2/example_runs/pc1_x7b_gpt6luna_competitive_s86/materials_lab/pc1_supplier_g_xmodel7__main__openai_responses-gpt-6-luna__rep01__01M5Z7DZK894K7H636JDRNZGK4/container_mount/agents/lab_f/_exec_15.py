import pandas as pd
D=pd.read_csv('records.csv');print(D.columns.tolist());print(D.head(2).to_string())