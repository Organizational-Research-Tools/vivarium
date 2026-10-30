
import pandas as pd
df = pd.read_csv("records.csv")
print(df.columns.tolist())
print(df[df['project_id'].str.startswith('QP-4476')][['project_id','prototype_id','property','mean','module_secondary_sheet']].to_string())
