import pandas as pd
D=pd.read_csv('records.csv'); print(D.shape); print(D.groupby(['project','prototype_id','instrument']).size().to_string())