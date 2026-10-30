
import pandas as pd
import numpy as np

df = pd.read_csv('records.csv')
print("Columns:", df.columns.tolist())
print("Shape:", df.shape)
print("\nFirst few rows:")
print(df.head(3).to_string())
