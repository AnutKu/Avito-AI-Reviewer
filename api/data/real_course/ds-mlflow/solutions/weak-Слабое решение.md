<!-- Извлечено из Product-part/01_Входящие/homework_examples/data_science/Пример домашки 1. (АА)/Слабое решение.html скриптом api/scripts/extract_homework.py. Не редактировать вручную. -->

versions Khanenko

In [2]:

%pip install numpy datasets scikit-learn mlflow==2.20.2

Requirement already satisfied: numpy in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (2.4.2)
Requirement already satisfied: datasets in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (4.0.0)
Requirement already satisfied: scikit-learn in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (1.8.0)
Requirement already satisfied: mlflow==2.20.2 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (2.20.2)
Requirement already satisfied: mlflow-skinny==2.20.2 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (2.20.2)
Requirement already satisfied: Flask<4 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (3.1.3)
Requirement already satisfied: Jinja2<4,>=3.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (3.1.6)
Requirement already satisfied: alembic!=1.10.0,<2 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (1.18.4)
Requirement already satisfied: docker<8,>=4.0.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (7.1.0)
Requirement already satisfied: graphene<4 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (3.4.3)
Requirement already satisfied: markdown<4,>=3.3 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (3.10.2)
Requirement already satisfied: matplotlib<4 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (3.10.8)
Requirement already satisfied: pandas<3 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (2.3.3)
Requirement already satisfied: pyarrow<19,>=4.0.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (18.1.0)
Requirement already satisfied: scipy<2 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (1.17.0)
Requirement already satisfied: sqlalchemy<3,>=1.4.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (2.0.49)
Requirement already satisfied: waitress<4 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow==2.20.2) (3.0.2)
Requirement already satisfied: cachetools<6,>=5.0.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (5.5.2)
Requirement already satisfied: click<9,>=7.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (8.3.1)
Requirement already satisfied: cloudpickle<4 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (3.1.2)
Requirement already satisfied: databricks-sdk<1,>=0.20.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (0.103.0)
Requirement already satisfied: gitpython<4,>=3.1.9 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (3.1.47)
Requirement already satisfied: importlib_metadata!=4.7.0,<9,>=3.7.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (8.7.1)
Requirement already satisfied: opentelemetry-api<3,>=1.9.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (1.41.0)
Requirement already satisfied: opentelemetry-sdk<3,>=1.9.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (1.41.0)
Requirement already satisfied: packaging<25 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (24.2)
Requirement already satisfied: protobuf<6,>=3.12.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (5.29.6)
Requirement already satisfied: pydantic<3,>=1.10.8 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (2.12.5)
Requirement already satisfied: pyyaml<7,>=5.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (6.0.3)
Requirement already satisfied: requests<3,>=2.17.3 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (2.32.5)
Requirement already satisfied: sqlparse<1,>=0.4.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (0.5.5)
Requirement already satisfied: typing-extensions<5,>=4.0.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (4.15.0)
Requirement already satisfied: joblib>=1.3.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from scikit-learn) (1.5.3)
Requirement already satisfied: threadpoolctl>=3.2.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from scikit-learn) (3.6.0)
Requirement already satisfied: Mako in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from alembic!=1.10.0,<2->mlflow==2.20.2) (1.3.11)
Requirement already satisfied: colorama in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from click<9,>=7.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (0.4.6)
Requirement already satisfied: google-auth~=2.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from databricks-sdk<1,>=0.20.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (2.49.2)
Requirement already satisfied: pywin32>=304 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from docker<8,>=4.0.0->mlflow==2.20.2) (311)
Requirement already satisfied: urllib3>=1.26.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from docker<8,>=4.0.0->mlflow==2.20.2) (2.6.2)
Requirement already satisfied: blinker>=1.9.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from Flask<4->mlflow==2.20.2) (1.9.0)
Requirement already satisfied: itsdangerous>=2.2.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from Flask<4->mlflow==2.20.2) (2.2.0)
Requirement already satisfied: markupsafe>=2.1.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from Flask<4->mlflow==2.20.2) (3.0.3)
Requirement already satisfied: werkzeug>=3.1.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from Flask<4->mlflow==2.20.2) (3.1.8)
Requirement already satisfied: gitdb<5,>=4.0.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from gitpython<4,>=3.1.9->mlflow-skinny==2.20.2->mlflow==2.20.2) (4.0.12)
Requirement already satisfied: smmap<6,>=3.0.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from gitdb<5,>=4.0.1->gitpython<4,>=3.1.9->mlflow-skinny==2.20.2->mlflow==2.20.2) (5.0.3)
Requirement already satisfied: pyasn1-modules>=0.2.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from google-auth~=2.0->databricks-sdk<1,>=0.20.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (0.4.2)
Requirement already satisfied: cryptography>=38.0.3 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from google-auth~=2.0->databricks-sdk<1,>=0.20.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (46.0.7)
Requirement already satisfied: graphql-core<3.3,>=3.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from graphene<4->mlflow==2.20.2) (3.2.8)
Requirement already satisfied: graphql-relay<3.3,>=3.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from graphene<4->mlflow==2.20.2) (3.2.0)
Requirement already satisfied: python-dateutil<3,>=2.7.0 in C:\Users\vhane\AppData\Roaming\Python\Python312\site-packages (from graphene<4->mlflow==2.20.2) (2.9.0.post0)
Requirement already satisfied: zipp>=3.20 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from importlib_metadata!=4.7.0,<9,>=3.7.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (3.23.1)
Requirement already satisfied: contourpy>=1.0.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from matplotlib<4->mlflow==2.20.2) (1.3.3)
Requirement already satisfied: cycler>=0.10 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from matplotlib<4->mlflow==2.20.2) (0.12.1)
Requirement already satisfied: fonttools>=4.22.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from matplotlib<4->mlflow==2.20.2) (4.61.1)
Requirement already satisfied: kiwisolver>=1.3.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from matplotlib<4->mlflow==2.20.2) (1.4.9)
Requirement already satisfied: pillow>=8 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from matplotlib<4->mlflow==2.20.2) (12.1.1)
Requirement already satisfied: pyparsing>=3 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from matplotlib<4->mlflow==2.20.2) (3.3.2)
Requirement already satisfied: opentelemetry-semantic-conventions==0.62b0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from opentelemetry-sdk<3,>=1.9.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (0.62b0)
Requirement already satisfied: pytz>=2020.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from pandas<3->mlflow==2.20.2) (2026.1.post1)
Requirement already satisfied: tzdata>=2022.7 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from pandas<3->mlflow==2.20.2) (2025.3)
Requirement already satisfied: annotated-types>=0.6.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from pydantic<3,>=1.10.8->mlflow-skinny==2.20.2->mlflow==2.20.2) (0.7.0)
Requirement already satisfied: pydantic-core==2.41.5 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from pydantic<3,>=1.10.8->mlflow-skinny==2.20.2->mlflow==2.20.2) (2.41.5)
Requirement already satisfied: typing-inspection>=0.4.2 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from pydantic<3,>=1.10.8->mlflow-skinny==2.20.2->mlflow==2.20.2) (0.4.2)
Requirement already satisfied: six>=1.5 in C:\Users\vhane\AppData\Roaming\Python\Python312\site-packages (from python-dateutil<3,>=2.7.0->graphene<4->mlflow==2.20.2) (1.17.0)
Requirement already satisfied: charset_normalizer<4,>=2 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from requests<3,>=2.17.3->mlflow-skinny==2.20.2->mlflow==2.20.2) (3.4.4)
Requirement already satisfied: idna<4,>=2.5 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from requests<3,>=2.17.3->mlflow-skinny==2.20.2->mlflow==2.20.2) (3.11)
Requirement already satisfied: certifi>=2017.4.17 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from requests<3,>=2.17.3->mlflow-skinny==2.20.2->mlflow==2.20.2) (2025.11.12)
Requirement already satisfied: greenlet>=1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from sqlalchemy<3,>=1.4.0->mlflow==2.20.2) (3.4.0)
Requirement already satisfied: filelock in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from datasets) (3.20.1)
Requirement already satisfied: dill<0.3.9,>=0.3.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from datasets) (0.3.8)
Requirement already satisfied: tqdm>=4.66.3 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from datasets) (4.67.3)
Requirement already satisfied: xxhash in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from datasets) (3.6.0)
Requirement already satisfied: multiprocess<0.70.17 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from datasets) (0.70.16)
Requirement already satisfied: fsspec<=2025.3.0,>=2023.1.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (2025.3.0)
Requirement already satisfied: huggingface-hub>=0.24.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from datasets) (1.11.0)
Requirement already satisfied: aiohttp!=4.0.0a0,!=4.0.0a1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (3.13.5)
Requirement already satisfied: aiohappyeyeballs>=2.5.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (2.6.1)
Requirement already satisfied: aiosignal>=1.4.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (1.4.0)
Requirement already satisfied: attrs>=17.3.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (26.1.0)
Requirement already satisfied: frozenlist>=1.1.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (1.8.0)
Requirement already satisfied: multidict<7.0,>=4.5 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (6.7.1)
Requirement already satisfied: propcache>=0.2.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (0.4.1)
Requirement already satisfied: yarl<2.0,>=1.17.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (1.23.0)
Requirement already satisfied: cffi>=2.0.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from cryptography>=38.0.3->google-auth~=2.0->databricks-sdk<1,>=0.20.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (2.0.0)
Requirement already satisfied: pycparser in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from cffi>=2.0.0->cryptography>=38.0.3->google-auth~=2.0->databricks-sdk<1,>=0.20.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (3.0)
Requirement already satisfied: hf-xet<2.0.0,>=1.4.3 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from huggingface-hub>=0.24.0->datasets) (1.4.3)
Requirement already satisfied: httpx<1,>=0.23.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from huggingface-hub>=0.24.0->datasets) (0.28.1)
Requirement already satisfied: typer in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from huggingface-hub>=0.24.0->datasets) (0.24.2)
Requirement already satisfied: anyio in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from httpx<1,>=0.23.0->huggingface-hub>=0.24.0->datasets) (4.12.0)
Requirement already satisfied: httpcore==1.* in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from httpx<1,>=0.23.0->huggingface-hub>=0.24.0->datasets) (1.0.9)
Requirement already satisfied: h11>=0.16 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from httpcore==1.*->httpx<1,>=0.23.0->huggingface-hub>=0.24.0->datasets) (0.16.0)
Requirement already satisfied: pyasn1<0.7.0,>=0.6.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from pyasn1-modules>=0.2.1->google-auth~=2.0->databricks-sdk<1,>=0.20.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (0.6.3)
Requirement already satisfied: shellingham>=1.3.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from typer->huggingface-hub>=0.24.0->datasets) (1.5.4)
Requirement already satisfied: rich>=12.3.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from typer->huggingface-hub>=0.24.0->datasets) (15.0.0)
Requirement already satisfied: annotated-doc>=0.0.2 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from typer->huggingface-hub>=0.24.0->datasets) (0.0.4)
Requirement already satisfied: markdown-it-py>=2.2.0 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from rich>=12.3.0->typer->huggingface-hub>=0.24.0->datasets) (4.0.0)
Requirement already satisfied: pygments<3.0.0,>=2.13.0 in C:\Users\vhane\AppData\Roaming\Python\Python312\site-packages (from rich>=12.3.0->typer->huggingface-hub>=0.24.0->datasets) (2.19.2)
Requirement already satisfied: mdurl~=0.1 in c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages (from markdown-it-py>=2.2.0->rich>=12.3.0->typer->huggingface-hub>=0.24.0->datasets) (0.1.2)
Note: you may need to restart the kernel to use updated packages.

Импорты¶

In [ ]:

import numpy as np
import random
import mlflow
import matplotlib.pyplot as plt
from datasets import load_dataset
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, precision_recall_curve, auc, ConfusionMatrixDisplay
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import OrdinalEncoder, StandardScaler, RobustScaler, MinMaxScaler

c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\tqdm\auto.py:21: TqdmWarning: IProgress not found. Please update jupyter and ipywidgets. See https://ipywidgets.readthedocs.io/en/stable/user_install.html
 from .autonotebook import tqdm as notebook_tqdm

In [4]:

mlflow.set_tracking_uri('http://158.160.242.172:5000/')
mlflow.set_experiment(experiment_id='23')

Out[4]:

<Experiment: artifact_location='mlflow-artifacts:/23', creation_time=1776882092588, experiment_id='23', last_update_time=1776882092588, lifecycle_stage='active', name='homework-dskhanenko', tags={}>

Константы¶

In [5]:

DATASET_NAME = 'scikit-learn/adult-census-income'
TEST_SIZE = 0.3
RANDOM_STATE = 42

random.seed(RANDOM_STATE)
np.random.seed(RANDOM_STATE)

In [6]:

def calculate_metrics(y_true, y_pred, y_proba):
 precision_vals, recall_vals, _ = precision_recall_curve(y_true, y_proba)
 return {
 "accuracy": accuracy_score(y_true, y_pred),
 "precision": precision_score(y_true, y_pred),
 "recall": recall_score(y_true, y_pred),
 "f1": f1_score(y_true, y_pred),
 "roc_auc": roc_auc_score(y_true, y_proba),
 "pr_auc": auc(recall_vals, precision_vals)
 }

def push_mlflow_experiment(pipeline, X_test, y_test, model_name, model_params, hypothesis, data_info):
 """
 pipeline: наш Pipeline
 X_test, y_test: тестовая выборка
 model_name: строка (условно 'LogisticRegression')
 model_params: словарь параметров модели
 hypothesis: описание гипотезы
 data_info: словарь с параметрами данных
 """

 with mlflow.start_run(run_name=f"{model_name}_{hypothesis[:15]}"):
 y_pred = pipeline.predict(X_test)
 y_proba = pipeline.predict_proba(X_test)[:, 1]

 metrics = calculate_metrics(y_test, y_pred, y_proba)

 mlflow.log_param("model_type", model_name)
 mlflow.log_params(model_params)
 mlflow.log_params(data_info)
 mlflow.set_tag("hypothesis", hypothesis)

 mlflow.log_metrics(metrics)

 cm_fig, ax = plt.subplots(figsize=(6, 5))
 ConfusionMatrixDisplay.from_predictions(y_test, y_pred, ax=ax, cmap='Blues')
 plt.title(f"CM: {hypothesis}")
 cm_path = "ConfMatrix.png"
 cm_fig.savefig(cm_path)
 mlflow.log_artifact(cm_path)
 plt.close(cm_fig)

 mlflow.sklearn.log_model(
 sk_model=pipeline,
 artifact_path="model",
 registered_model_name="ClassificationModel"
 )

Скачивание и подготовка данных¶

In [7]:

dataset = load_dataset('scikit-learn/adult-census-income')
df = dataset['train'].to_pandas()

target_column = 'income'
df[target_column] = (df[target_column] == '>50K').astype(int)

columns = [
 'age', 'workclass', 'fnlwgt', 'education', 'education.num',
 'marital.status', 'occupation', 'relationship', 'race', 'sex',
 'capital.gain', 'capital.loss', 'hours.per.week', 'native.country'
]

cat_features = ['workclass', 'education', 'marital.status', 'occupation', 'relationship', 'race', 'sex', 'native.country']
num_features = ['age', 'fnlwgt', 'education.num', 'capital.gain', 'capital.loss', 'hours.per.week']

Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.

In [8]:

from sklearn.preprocessing import OneHotEncoder, TargetEncoder

X = df[columns]
y = df[target_column]

X_train, X_test, y_train, y_test = train_test_split(
 X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
)

preprocessor = ColumnTransformer(
 transformers=[
 ('cat', OneHotEncoder(handle_unknown='ignore'), cat_features),
 ('num', StandardScaler(), num_features),
 ]
)

preprocessor

Out[8]:

 ColumnTransformer(transformers=[('cat', OneHotEncoder(handle_unknown='ignore'),
 ['workclass', 'education', 'marital.status',
 'occupation', 'relationship', 'race', 'sex',
 'native.country']),
 ('num', StandardScaler(),
 ['age', 'fnlwgt', 'education.num',
 'capital.gain', 'capital.loss',
 'hours.per.week'])])
In a Jupyter environment, please rerun this cell to show the HTML representation or trust the notebook.
On GitHub, the HTML representation is unable to render, please try loading this page with nbviewer.org.
ColumnTransformer

?Documentation for ColumnTransformeriNot fitted

Parameters

 transformers
 transformers: list of tuples

List of (name, transformer, columns) tuples specifying the
transformer objects to be applied to subsets of the data.

name : str
 Like in Pipeline and FeatureUnion, this allows the transformer and
 its parameters to be set using ``set_params`` and searched in grid
 search.
transformer : {'drop', 'passthrough'} or estimator
 Estimator must support :term:`fit` and :term:`transform`.
 Special-cased strings 'drop' and 'passthrough' are accepted as
 well, to indicate to drop the columns or to pass them through
 untransformed, respectively.
columns : str, array-like of str, int, array-like of int, array-like of bool, slice or callable
 Indexes the data on its second axis. Integers are interpreted as
 positional columns, while strings can reference DataFrame columns
 by name. A scalar string or int should be used where
 ``transformer`` expects X to be a 1d array-like (vector),
 otherwise a 2d array will be passed to the transformer.
 A callable is passed the input data `X` and can return any of the
 above. To select multiple columns by name or dtype, you can use
 :obj:`make_column_selector`.

[('cat', ...), ('num', ...)]

 remainder
 remainder: {'drop', 'passthrough'} or estimator, default='drop'

By default, only the specified columns in `transformers` are
transformed and combined in the output, and the non-specified
columns are dropped. (default of ``'drop'``).
By specifying ``remainder='passthrough'``, all remaining columns that
were not specified in `transformers`, but present in the data passed
to `fit` will be automatically passed through. This subset of columns
is concatenated with the output of the transformers. For dataframes,
extra columns not seen during `fit` will be excluded from the output
of `transform`.
By setting ``remainder`` to be an estimator, the remaining
non-specified columns will use the ``remainder`` estimator. The
estimator must support :term:`fit` and :term:`transform`.
Note that using this feature requires that the DataFrame columns
input at :term:`fit` and :term:`transform` have identical order.

'drop'

 sparse_threshold
 sparse_threshold: float, default=0.3

If the output of the different transformers contains sparse matrices,
these will be stacked as a sparse matrix if the overall density is
lower than this value. Use ``sparse_threshold=0`` to always return
dense. When the transformed output consists of all dense data, the
stacked result will be dense, and this keyword will be ignored.

0.3

 n_jobs
 n_jobs: int, default=None

Number of jobs to run in parallel.
``None`` means 1 unless in a :obj:`joblib.parallel_backend` context.
``-1`` means using all processors. See :term:`Glossary `
for more details.

None

 transformer_weights
 transformer_weights: dict, default=None

Multiplicative weights for features per transformer. The output of the
transformer is multiplied by these weights. Keys are transformer names,
values the weights.

None

 verbose
 verbose: bool, default=False

If True, the time elapsed while fitting each transformer will be
printed as it is completed.

False

 verbose_feature_names_out
 verbose_feature_names_out: bool, str or Callable[[str, str], str], default=True

- If True, :meth:`ColumnTransformer.get_feature_names_out` will prefix
 all feature names with the name of the transformer that generated that
 feature. It is equivalent to setting
 `verbose_feature_names_out="{transformer_name}__{feature_name}"`.
- If False, :meth:`ColumnTransformer.get_feature_names_out` will not
 prefix any feature names and will error if feature names are not
 unique.
- If ``Callable[[str, str], str]``,
 :meth:`ColumnTransformer.get_feature_names_out` will rename all the features
 using the name of the transformer. The first argument of the callable is the
 transformer name and the second argument is the feature name. The returned
 string will be the new feature name.
- If ``str``, it must be a string ready for formatting. The given string will
 be formatted using two field names: ``transformer_name`` and ``feature_name``.
 e.g. ``"{feature_name}__{transformer_name}"``. See :meth:`str.format` method
 from the standard library for more info.

.. versionadded:: 1.0

.. versionchanged:: 1.6
 `verbose_feature_names_out` can be a callable or a string to be formatted.

True

 force_int_remainder_cols
 force_int_remainder_cols: bool, default=False

This parameter has no effect.

.. note::
 If you do not access the list of columns for the remainder columns
 in the `transformers_` fitted attribute, you do not need to set
 this parameter.

.. versionadded:: 1.5

.. versionchanged:: 1.7
 The default value for `force_int_remainder_cols` will change from
 `True` to `False` in version 1.7.

.. deprecated:: 1.7
 `force_int_remainder_cols` is deprecated and will be removed in 1.9.

'deprecated'

cat

['workclass', 'education', 'marital.status', 'occupation', 'relationship', 'race', 'sex', 'native.country']

OneHotEncoder

?Documentation for OneHotEncoder

Parameters

 categories
 categories: 'auto' or a list of array-like, default='auto'

Categories (unique values) per feature:

- 'auto' : Determine categories automatically from the training data.
- list : ``categories[i]`` holds the categories expected in the ith
 column. The passed categories should not mix strings and numeric
 values within a single feature, and should be sorted in case of
 numeric values.

The used categories can be found in the ``categories_`` attribute.

.. versionadded:: 0.20

'auto'

 drop
 drop: {'first', 'if_binary'} or an array-like of shape (n_features,), default=None

Specifies a methodology to use to drop one of the categories per
feature. This is useful in situations where perfectly collinear
features cause problems, such as when feeding the resulting data
into an unregularized linear regression model.

However, dropping one category breaks the symmetry of the original
representation and can therefore induce a bias in downstream models,
for instance for penalized linear classification or regression models.

- None : retain all features (the default).
- 'first' : drop the first category in each feature. If only one
 category is present, the feature will be dropped entirely.
- 'if_binary' : drop the first category in each feature with two
 categories. Features with 1 or more than 2 categories are
 left intact.
- array : ``drop[i]`` is the category in feature ``X[:, i]`` that
 should be dropped.

When `max_categories` or `min_frequency` is configured to group
infrequent categories, the dropping behavior is handled after the
grouping.

.. versionadded:: 0.21
 The parameter `drop` was added in 0.21.

.. versionchanged:: 0.23
 The option `drop='if_binary'` was added in 0.23.

.. versionchanged:: 1.1
 Support for dropping infrequent categories.

None

 sparse_output
 sparse_output: bool, default=True

When ``True``, it returns a :class:`scipy.sparse.csr_matrix`,
i.e. a sparse matrix in "Compressed Sparse Row" (CSR) format.

.. versionadded:: 1.2
 `sparse` was renamed to `sparse_output`

True

 dtype
 dtype: number type, default=np.float64

Desired dtype of output.

<class 'numpy.float64'>

 handle_unknown
 handle_unknown: {'error', 'ignore', 'infrequent_if_exist', 'warn'}, default='error'

Specifies the way unknown categories are handled during :meth:`transform`.

- 'error' : Raise an error if an unknown category is present during transform.
- 'ignore' : When an unknown category is encountered during
 transform, the resulting one-hot encoded columns for this feature
 will be all zeros. In the inverse transform, an unknown category
 will be denoted as None.
- 'infrequent_if_exist' : When an unknown category is encountered
 during transform, the resulting one-hot encoded columns for this
 feature will map to the infrequent category if it exists. The
 infrequent category will be mapped to the last position in the
 encoding. During inverse transform, an unknown category will be
 mapped to the category denoted `'infrequent'` if it exists. If the
 `'infrequent'` category does not exist, then :meth:`transform` and
 :meth:`inverse_transform` will handle an unknown category as with
 `handle_unknown='ignore'`. Infrequent categories exist based on
 `min_frequency` and `max_categories`. Read more in the
 :ref:`User Guide `.
- 'warn' : When an unknown category is encountered during transform
 a warning is issued, and the encoding then proceeds as described for
 `handle_unknown="infrequent_if_exist"`.

.. versionchanged:: 1.1
 `'infrequent_if_exist'` was added to automatically handle unknown
 categories and infrequent categories.

.. versionadded:: 1.6
 The option `"warn"` was added in 1.6.

'ignore'

 min_frequency
 min_frequency: int or float, default=None

Specifies the minimum frequency below which a category will be
considered infrequent.

- If `int`, categories with a smaller cardinality will be considered
 infrequent.

- If `float`, categories with a smaller cardinality than
 `min_frequency * n_samples` will be considered infrequent.

.. versionadded:: 1.1
 Read more in the :ref:`User Guide `.

None

 max_categories
 max_categories: int, default=None

Specifies an upper limit to the number of output features for each input
feature when considering infrequent categories. If there are infrequent
categories, `max_categories` includes the category representing the
infrequent categories along with the frequent categories. If `None`,
there is no limit to the number of output features.

.. versionadded:: 1.1
 Read more in the :ref:`User Guide `.

None

 feature_name_combiner
 feature_name_combiner: "concat" or callable, default="concat"

Callable with signature `def callable(input_feature, category)` that returns a
string. This is used to create feature names to be returned by
:meth:`get_feature_names_out`.

`"concat"` concatenates encoded feature name and category with
`feature + "_" + str(category)`.E.g. feature X with values 1, 6, 7 create
feature names `X_1, X_6, X_7`.

.. versionadded:: 1.3

'concat'

num

['age', 'fnlwgt', 'education.num', 'capital.gain', 'capital.loss', 'hours.per.week']

StandardScaler

?Documentation for StandardScaler

Parameters

 copy
 copy: bool, default=True

If False, try to avoid a copy and do inplace scaling instead.
This is not guaranteed to always work inplace; e.g. if the data is
not a NumPy array or scipy.sparse CSR matrix, a copy may still be
returned.

True

 with_mean
 with_mean: bool, default=True

If True, center the data before scaling.
This does not work (and will raise an exception) when attempted on
sparse matrices, because centering them entails building a dense
matrix which in common use cases is likely to be too large to fit in
memory.

True

 with_std
 with_std: bool, default=True

If True, scale the data to unit variance (or equivalently,
unit standard deviation).

True

Обучение модели¶

В качестве бейзлайна возьмём логистическую регрессию

In [9]:

model_params = dict(
 penalty='l2', C=1, solver='newton-cg', max_iter=100, random_state=RANDOM_STATE
)
model_params

Out[9]:

{'penalty': 'l2',
 'C': 1,
 'solver': 'newton-cg',
 'max_iter': 100,
 'random_state': 42}

In [10]:

model = LogisticRegression(**model_params)
model

Out[10]:

 LogisticRegression(C=1, penalty='l2', random_state=42, solver='newton-cg')
In a Jupyter environment, please rerun this cell to show the HTML representation or trust the notebook.
On GitHub, the HTML representation is unable to render, please try loading this page with nbviewer.org.
LogisticRegression

?Documentation for LogisticRegressioniNot fitted

Parameters

 penalty
 penalty: {'l1', 'l2', 'elasticnet', None}, default='l2'

Specify the norm of the penalty:

- `None`: no penalty is added;
- `'l2'`: add a L2 penalty term and it is the default choice;
- `'l1'`: add a L1 penalty term;
- `'elasticnet'`: both L1 and L2 penalty terms are added.

.. warning::
 Some penalties may not work with some solvers. See the parameter
 `solver` below, to know the compatibility between the penalty and
 solver.

.. versionadded:: 0.19
 l1 penalty with SAGA solver (allowing 'multinomial' + L1)

.. deprecated:: 1.8
 `penalty` was deprecated in version 1.8 and will be removed in 1.10.
 Use `l1_ratio` instead. `l1_ratio=0` for `penalty='l2'`, `l1_ratio=1` for
 `penalty='l1'` and `l1_ratio` set to any float between 0 and 1 for
 `'penalty='elasticnet'`.

'l2'

 C
 C: float, default=1.0

Inverse of regularization strength; must be a positive float.
Like in support vector machines, smaller values specify stronger
regularization. `C=np.inf` results in unpenalized logistic regression.
For a visual example on the effect of tuning the `C` parameter
with an L1 penalty, see:
:ref:`sphx_glr_auto_examples_linear_model_plot_logistic_path.py`.

1

 l1_ratio
 l1_ratio: float, default=0.0

The Elastic-Net mixing parameter, with `0 <= l1_ratio <= 1`. Setting
`l1_ratio=1` gives a pure L1-penalty, setting `l1_ratio=0` a pure L2-penalty.
Any value between 0 and 1 gives an Elastic-Net penalty of the form
`l1_ratio * L1 + (1 - l1_ratio) * L2`.

.. warning::
 Certain values of `l1_ratio`, i.e. some penalties, may not work with some
 solvers. See the parameter `solver` below, to know the compatibility between
 the penalty and solver.

.. versionchanged:: 1.8
 Default value changed from None to 0.0.

.. deprecated:: 1.8
 `None` is deprecated and will be removed in version 1.10. Always use
 `l1_ratio` to specify the penalty type.

0.0

 dual
 dual: bool, default=False

Dual (constrained) or primal (regularized, see also
:ref:`this equation `) formulation. Dual formulation
is only implemented for l2 penalty with liblinear solver. Prefer `dual=False`
when n_samples > n_features.

False

 tol
 tol: float, default=1e-4

Tolerance for stopping criteria.

0.0001

 fit_intercept
 fit_intercept: bool, default=True

Specifies if a constant (a.k.a. bias or intercept) should be
added to the decision function.

True

 intercept_scaling
 intercept_scaling: float, default=1

Useful only when the solver `liblinear` is used
and `self.fit_intercept` is set to `True`. In this case, `x` becomes
`[x, self.intercept_scaling]`,
i.e. a "synthetic" feature with constant value equal to
`intercept_scaling` is appended to the instance vector.
The intercept becomes
``intercept_scaling * synthetic_feature_weight``.

.. note::
 The synthetic feature weight is subject to L1 or L2
 regularization as all other features.
 To lessen the effect of regularization on synthetic feature weight
 (and therefore on the intercept) `intercept_scaling` has to be increased.

1

 class_weight
 class_weight: dict or 'balanced', default=None

Weights associated with classes in the form ``{class_label: weight}``.
If not given, all classes are supposed to have weight one.

The "balanced" mode uses the values of y to automatically adjust
weights inversely proportional to class frequencies in the input data
as ``n_samples / (n_classes * np.bincount(y))``.

Note that these weights will be multiplied with sample_weight (passed
through the fit method) if sample_weight is specified.

.. versionadded:: 0.17
 *class_weight='balanced'*

None

 random_state
 random_state: int, RandomState instance, default=None

Used when ``solver`` == 'sag', 'saga' or 'liblinear' to shuffle the
data. See :term:`Glossary ` for details.

42

 solver
 solver: {'lbfgs', 'liblinear', 'newton-cg', 'newton-cholesky', 'sag', 'saga'}, default='lbfgs'

Algorithm to use in the optimization problem. Default is 'lbfgs'.
To choose a solver, you might want to consider the following aspects:

- 'lbfgs' is a good default solver because it works reasonably well for a wide
 class of problems.
- For :term:`multiclass` problems (`n_classes >= 3`), all solvers except
 'liblinear' minimize the full multinomial loss, 'liblinear' will raise an
 error.
- 'newton-cholesky' is a good choice for
 `n_samples` >> `n_features * n_classes`, especially with one-hot encoded
 categorical features with rare categories. Be aware that the memory usage
 of this solver has a quadratic dependency on `n_features * n_classes`
 because it explicitly computes the full Hessian matrix.
- For small datasets, 'liblinear' is a good choice, whereas 'sag'
 and 'saga' are faster for large ones;
- 'liblinear' can only handle binary classification by default. To apply a
 one-versus-rest scheme for the multiclass setting one can wrap it with the
 :class:`~sklearn.multiclass.OneVsRestClassifier`.

.. warning::
 The choice of the algorithm depends on the penalty chosen (`l1_ratio=0`
 for L2-penalty, `l1_ratio=1` for L1-penalty and `0 < l1_ratio < 1` for
 Elastic-Net) and on (multinomial) multiclass support:

 ================= ======================== ======================
 solver l1_ratio multinomial multiclass
 ================= ======================== ======================
 'lbfgs' l1_ratio=0 yes
 'liblinear' l1_ratio=1 or l1_ratio=0 no
 'newton-cg' l1_ratio=0 yes
 'newton-cholesky' l1_ratio=0 yes
 'sag' l1_ratio=0 yes
 'saga' 0<=l1_ratio<=1 yes
 ================= ======================== ======================

.. note::
 'sag' and 'saga' fast convergence is only guaranteed on features
 with approximately the same scale. You can preprocess the data with
 a scaler from :mod:`sklearn.preprocessing`.

.. seealso::
 Refer to the :ref:`User Guide ` for more
 information regarding :class:`LogisticRegression` and more specifically the
 :ref:`Table `
 summarizing solver/penalty supports.

.. versionadded:: 0.17
 Stochastic Average Gradient (SAG) descent solver. Multinomial support in
 version 0.18.
.. versionadded:: 0.19
 SAGA solver.
.. versionchanged:: 0.22
 The default solver changed from 'liblinear' to 'lbfgs' in 0.22.
.. versionadded:: 1.2
 newton-cholesky solver. Multinomial support in version 1.6.

'newton-cg'

 max_iter
 max_iter: int, default=100

Maximum number of iterations taken for the solvers to converge.

100

 verbose
 verbose: int, default=0

For the liblinear and lbfgs solvers set verbose to any positive
number for verbosity.

0

 warm_start
 warm_start: bool, default=False

When set to True, reuse the solution of the previous call to fit as
initialization, otherwise, just erase the previous solution.
Useless for liblinear solver. See :term:`the Glossary `.

.. versionadded:: 0.17
 *warm_start* to support *lbfgs*, *newton-cg*, *sag*, *saga* solvers.

False

 n_jobs
 n_jobs: int, default=None

Does not have any effect.

.. deprecated:: 1.8
 `n_jobs` is deprecated in version 1.8 and will be removed in 1.10.

None

Соберем пайплайн целиком

In [11]:

pipeline = Pipeline([
 ('preprocess', preprocessor),
 ('model', model)
])
pipeline.fit(X_train, y_train)
pipeline

c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\sklearn\linear_model\_logistic.py:1135: FutureWarning: 'penalty' was deprecated in version 1.8 and will be removed in 1.10. To avoid this warning, leave 'penalty' set to its default value and use 'l1_ratio' or 'C' instead. Use l1_ratio=0 instead of penalty='l2', l1_ratio=1 instead of penalty='l1', and C=np.inf instead of penalty=None.
 warnings.warn(

Out[11]:

 Pipeline(steps=[('preprocess',
 ColumnTransformer(transformers=[('cat',
 OneHotEncoder(handle_unknown='ignore'),
 ['workclass', 'education',
 'marital.status',
 'occupation', 'relationship',
 'race', 'sex',
 'native.country']),
 ('num', StandardScaler(),
 ['age', 'fnlwgt',
 'education.num',
 'capital.gain',
 'capital.loss',
 'hours.per.week'])])),
 ('model',
 LogisticRegression(C=1, penalty='l2', random_state=42,
 solver='newton-cg'))])
In a Jupyter environment, please rerun this cell to show the HTML representation or trust the notebook.
On GitHub, the HTML representation is unable to render, please try loading this page with nbviewer.org.
Pipeline

?Documentation for PipelineiFitted

Parameters

 steps
 steps: list of tuples

List of (name of step, estimator) tuples that are to be chained in
sequential order. To be compatible with the scikit-learn API, all steps
must define `fit`. All non-last steps must also define `transform`. See
:ref:`Combining Estimators ` for more details.

[('preprocess', ...), ('model', ...)]

 transform_input
 transform_input: list of str, default=None

The names of the :term:`metadata` parameters that should be transformed by the
pipeline before passing it to the step consuming it.

This enables transforming some input arguments to ``fit`` (other than ``X``)
to be transformed by the steps of the pipeline up to the step which requires
them. Requirement is defined via :ref:`metadata routing `.
For instance, this can be used to pass a validation set through the pipeline.

You can only set this if metadata routing is enabled, which you
can enable using ``sklearn.set_config(enable_metadata_routing=True)``.

.. versionadded:: 1.6

None

 memory
 memory: str or object with the joblib.Memory interface, default=None

Used to cache the fitted transformers of the pipeline. The last step
will never be cached, even if it is a transformer. By default, no
caching is performed. If a string is given, it is the path to the
caching directory. Enabling caching triggers a clone of the transformers
before fitting. Therefore, the transformer instance given to the
pipeline cannot be inspected directly. Use the attribute ``named_steps``
or ``steps`` to inspect estimators within the pipeline. Caching the
transformers is advantageous when fitting is time consuming. See
:ref:`sphx_glr_auto_examples_neighbors_plot_caching_nearest_neighbors.py`
for an example on how to enable caching.

None

 verbose
 verbose: bool, default=False

If True, the time elapsed while fitting each step will be printed as it
is completed.

False

preprocess: ColumnTransformer

?Documentation for preprocess: ColumnTransformer

Parameters

 transformers
 transformers: list of tuples

List of (name, transformer, columns) tuples specifying the
transformer objects to be applied to subsets of the data.

name : str
 Like in Pipeline and FeatureUnion, this allows the transformer and
 its parameters to be set using ``set_params`` and searched in grid
 search.
transformer : {'drop', 'passthrough'} or estimator
 Estimator must support :term:`fit` and :term:`transform`.
 Special-cased strings 'drop' and 'passthrough' are accepted as
 well, to indicate to drop the columns or to pass them through
 untransformed, respectively.
columns : str, array-like of str, int, array-like of int, array-like of bool, slice or callable
 Indexes the data on its second axis. Integers are interpreted as
 positional columns, while strings can reference DataFrame columns
 by name. A scalar string or int should be used where
 ``transformer`` expects X to be a 1d array-like (vector),
 otherwise a 2d array will be passed to the transformer.
 A callable is passed the input data `X` and can return any of the
 above. To select multiple columns by name or dtype, you can use
 :obj:`make_column_selector`.

[('cat', ...), ('num', ...)]

 remainder
 remainder: {'drop', 'passthrough'} or estimator, default='drop'

By default, only the specified columns in `transformers` are
transformed and combined in the output, and the non-specified
columns are dropped. (default of ``'drop'``).
By specifying ``remainder='passthrough'``, all remaining columns that
were not specified in `transformers`, but present in the data passed
to `fit` will be automatically passed through. This subset of columns
is concatenated with the output of the transformers. For dataframes,
extra columns not seen during `fit` will be excluded from the output
of `transform`.
By setting ``remainder`` to be an estimator, the remaining
non-specified columns will use the ``remainder`` estimator. The
estimator must support :term:`fit` and :term:`transform`.
Note that using this feature requires that the DataFrame columns
input at :term:`fit` and :term:`transform` have identical order.

'drop'

 sparse_threshold
 sparse_threshold: float, default=0.3

If the output of the different transformers contains sparse matrices,
these will be stacked as a sparse matrix if the overall density is
lower than this value. Use ``sparse_threshold=0`` to always return
dense. When the transformed output consists of all dense data, the
stacked result will be dense, and this keyword will be ignored.

0.3

 n_jobs
 n_jobs: int, default=None

Number of jobs to run in parallel.
``None`` means 1 unless in a :obj:`joblib.parallel_backend` context.
``-1`` means using all processors. See :term:`Glossary `
for more details.

None

 transformer_weights
 transformer_weights: dict, default=None

Multiplicative weights for features per transformer. The output of the
transformer is multiplied by these weights. Keys are transformer names,
values the weights.

None

 verbose
 verbose: bool, default=False

If True, the time elapsed while fitting each transformer will be
printed as it is completed.

False

 verbose_feature_names_out
 verbose_feature_names_out: bool, str or Callable[[str, str], str], default=True

- If True, :meth:`ColumnTransformer.get_feature_names_out` will prefix
 all feature names with the name of the transformer that generated that
 feature. It is equivalent to setting
 `verbose_feature_names_out="{transformer_name}__{feature_name}"`.
- If False, :meth:`ColumnTransformer.get_feature_names_out` will not
 prefix any feature names and will error if feature names are not
 unique.
- If ``Callable[[str, str], str]``,
 :meth:`ColumnTransformer.get_feature_names_out` will rename all the features
 using the name of the transformer. The first argument of the callable is the
 transformer name and the second argument is the feature name. The returned
 string will be the new feature name.
- If ``str``, it must be a string ready for formatting. The given string will
 be formatted using two field names: ``transformer_name`` and ``feature_name``.
 e.g. ``"{feature_name}__{transformer_name}"``. See :meth:`str.format` method
 from the standard library for more info.

.. versionadded:: 1.0

.. versionchanged:: 1.6
 `verbose_feature_names_out` can be a callable or a string to be formatted.

True

 force_int_remainder_cols
 force_int_remainder_cols: bool, default=False

This parameter has no effect.

.. note::
 If you do not access the list of columns for the remainder columns
 in the `transformers_` fitted attribute, you do not need to set
 this parameter.

.. versionadded:: 1.5

.. versionchanged:: 1.7
 The default value for `force_int_remainder_cols` will change from
 `True` to `False` in version 1.7.

.. deprecated:: 1.7
 `force_int_remainder_cols` is deprecated and will be removed in 1.9.

'deprecated'

cat

['workclass', 'education', 'marital.status', 'occupation', 'relationship', 'race', 'sex', 'native.country']

OneHotEncoder

?Documentation for OneHotEncoder

Parameters

 categories
 categories: 'auto' or a list of array-like, default='auto'

Categories (unique values) per feature:

- 'auto' : Determine categories automatically from the training data.
- list : ``categories[i]`` holds the categories expected in the ith
 column. The passed categories should not mix strings and numeric
 values within a single feature, and should be sorted in case of
 numeric values.

The used categories can be found in the ``categories_`` attribute.

.. versionadded:: 0.20

'auto'

 drop
 drop: {'first', 'if_binary'} or an array-like of shape (n_features,), default=None

Specifies a methodology to use to drop one of the categories per
feature. This is useful in situations where perfectly collinear
features cause problems, such as when feeding the resulting data
into an unregularized linear regression model.

However, dropping one category breaks the symmetry of the original
representation and can therefore induce a bias in downstream models,
for instance for penalized linear classification or regression models.

- None : retain all features (the default).
- 'first' : drop the first category in each feature. If only one
 category is present, the feature will be dropped entirely.
- 'if_binary' : drop the first category in each feature with two
 categories. Features with 1 or more than 2 categories are
 left intact.
- array : ``drop[i]`` is the category in feature ``X[:, i]`` that
 should be dropped.

When `max_categories` or `min_frequency` is configured to group
infrequent categories, the dropping behavior is handled after the
grouping.

.. versionadded:: 0.21
 The parameter `drop` was added in 0.21.

.. versionchanged:: 0.23
 The option `drop='if_binary'` was added in 0.23.

.. versionchanged:: 1.1
 Support for dropping infrequent categories.

None

 sparse_output
 sparse_output: bool, default=True

When ``True``, it returns a :class:`scipy.sparse.csr_matrix`,
i.e. a sparse matrix in "Compressed Sparse Row" (CSR) format.

.. versionadded:: 1.2
 `sparse` was renamed to `sparse_output`

True

 dtype
 dtype: number type, default=np.float64

Desired dtype of output.

<class 'numpy.float64'>

 handle_unknown
 handle_unknown: {'error', 'ignore', 'infrequent_if_exist', 'warn'}, default='error'

Specifies the way unknown categories are handled during :meth:`transform`.

- 'error' : Raise an error if an unknown category is present during transform.
- 'ignore' : When an unknown category is encountered during
 transform, the resulting one-hot encoded columns for this feature
 will be all zeros. In the inverse transform, an unknown category
 will be denoted as None.
- 'infrequent_if_exist' : When an unknown category is encountered
 during transform, the resulting one-hot encoded columns for this
 feature will map to the infrequent category if it exists. The
 infrequent category will be mapped to the last position in the
 encoding. During inverse transform, an unknown category will be
 mapped to the category denoted `'infrequent'` if it exists. If the
 `'infrequent'` category does not exist, then :meth:`transform` and
 :meth:`inverse_transform` will handle an unknown category as with
 `handle_unknown='ignore'`. Infrequent categories exist based on
 `min_frequency` and `max_categories`. Read more in the
 :ref:`User Guide `.
- 'warn' : When an unknown category is encountered during transform
 a warning is issued, and the encoding then proceeds as described for
 `handle_unknown="infrequent_if_exist"`.

.. versionchanged:: 1.1
 `'infrequent_if_exist'` was added to automatically handle unknown
 categories and infrequent categories.

.. versionadded:: 1.6
 The option `"warn"` was added in 1.6.

'ignore'

 min_frequency
 min_frequency: int or float, default=None

Specifies the minimum frequency below which a category will be
considered infrequent.

- If `int`, categories with a smaller cardinality will be considered
 infrequent.

- If `float`, categories with a smaller cardinality than
 `min_frequency * n_samples` will be considered infrequent.

.. versionadded:: 1.1
 Read more in the :ref:`User Guide `.

None

 max_categories
 max_categories: int, default=None

Specifies an upper limit to the number of output features for each input
feature when considering infrequent categories. If there are infrequent
categories, `max_categories` includes the category representing the
infrequent categories along with the frequent categories. If `None`,
there is no limit to the number of output features.

.. versionadded:: 1.1
 Read more in the :ref:`User Guide `.

None

 feature_name_combiner
 feature_name_combiner: "concat" or callable, default="concat"

Callable with signature `def callable(input_feature, category)` that returns a
string. This is used to create feature names to be returned by
:meth:`get_feature_names_out`.

`"concat"` concatenates encoded feature name and category with
`feature + "_" + str(category)`.E.g. feature X with values 1, 6, 7 create
feature names `X_1, X_6, X_7`.

.. versionadded:: 1.3

'concat'

num

['age', 'fnlwgt', 'education.num', 'capital.gain', 'capital.loss', 'hours.per.week']

StandardScaler

?Documentation for StandardScaler

Parameters

 copy
 copy: bool, default=True

If False, try to avoid a copy and do inplace scaling instead.
This is not guaranteed to always work inplace; e.g. if the data is
not a NumPy array or scipy.sparse CSR matrix, a copy may still be
returned.

True

 with_mean
 with_mean: bool, default=True

If True, center the data before scaling.
This does not work (and will raise an exception) when attempted on
sparse matrices, because centering them entails building a dense
matrix which in common use cases is likely to be too large to fit in
memory.

True

 with_std
 with_std: bool, default=True

If True, scale the data to unit variance (or equivalently,
unit standard deviation).

True

LogisticRegression

?Documentation for LogisticRegression

Parameters

 penalty
 penalty: {'l1', 'l2', 'elasticnet', None}, default='l2'

Specify the norm of the penalty:

- `None`: no penalty is added;
- `'l2'`: add a L2 penalty term and it is the default choice;
- `'l1'`: add a L1 penalty term;
- `'elasticnet'`: both L1 and L2 penalty terms are added.

.. warning::
 Some penalties may not work with some solvers. See the parameter
 `solver` below, to know the compatibility between the penalty and
 solver.

.. versionadded:: 0.19
 l1 penalty with SAGA solver (allowing 'multinomial' + L1)

.. deprecated:: 1.8
 `penalty` was deprecated in version 1.8 and will be removed in 1.10.
 Use `l1_ratio` instead. `l1_ratio=0` for `penalty='l2'`, `l1_ratio=1` for
 `penalty='l1'` and `l1_ratio` set to any float between 0 and 1 for
 `'penalty='elasticnet'`.

'l2'

 C
 C: float, default=1.0

Inverse of regularization strength; must be a positive float.
Like in support vector machines, smaller values specify stronger
regularization. `C=np.inf` results in unpenalized logistic regression.
For a visual example on the effect of tuning the `C` parameter
with an L1 penalty, see:
:ref:`sphx_glr_auto_examples_linear_model_plot_logistic_path.py`.

1

 l1_ratio
 l1_ratio: float, default=0.0

The Elastic-Net mixing parameter, with `0 <= l1_ratio <= 1`. Setting
`l1_ratio=1` gives a pure L1-penalty, setting `l1_ratio=0` a pure L2-penalty.
Any value between 0 and 1 gives an Elastic-Net penalty of the form
`l1_ratio * L1 + (1 - l1_ratio) * L2`.

.. warning::
 Certain values of `l1_ratio`, i.e. some penalties, may not work with some
 solvers. See the parameter `solver` below, to know the compatibility between
 the penalty and solver.

.. versionchanged:: 1.8
 Default value changed from None to 0.0.

.. deprecated:: 1.8
 `None` is deprecated and will be removed in version 1.10. Always use
 `l1_ratio` to specify the penalty type.

0.0

 dual
 dual: bool, default=False

Dual (constrained) or primal (regularized, see also
:ref:`this equation `) formulation. Dual formulation
is only implemented for l2 penalty with liblinear solver. Prefer `dual=False`
when n_samples > n_features.

False

 tol
 tol: float, default=1e-4

Tolerance for stopping criteria.

0.0001

 fit_intercept
 fit_intercept: bool, default=True

Specifies if a constant (a.k.a. bias or intercept) should be
added to the decision function.

True

 intercept_scaling
 intercept_scaling: float, default=1

Useful only when the solver `liblinear` is used
and `self.fit_intercept` is set to `True`. In this case, `x` becomes
`[x, self.intercept_scaling]`,
i.e. a "synthetic" feature with constant value equal to
`intercept_scaling` is appended to the instance vector.
The intercept becomes
``intercept_scaling * synthetic_feature_weight``.

.. note::
 The synthetic feature weight is subject to L1 or L2
 regularization as all other features.
 To lessen the effect of regularization on synthetic feature weight
 (and therefore on the intercept) `intercept_scaling` has to be increased.

1

 class_weight
 class_weight: dict or 'balanced', default=None

Weights associated with classes in the form ``{class_label: weight}``.
If not given, all classes are supposed to have weight one.

The "balanced" mode uses the values of y to automatically adjust
weights inversely proportional to class frequencies in the input data
as ``n_samples / (n_classes * np.bincount(y))``.

Note that these weights will be multiplied with sample_weight (passed
through the fit method) if sample_weight is specified.

.. versionadded:: 0.17
 *class_weight='balanced'*

None

 random_state
 random_state: int, RandomState instance, default=None

Used when ``solver`` == 'sag', 'saga' or 'liblinear' to shuffle the
data. See :term:`Glossary ` for details.

42

 solver
 solver: {'lbfgs', 'liblinear', 'newton-cg', 'newton-cholesky', 'sag', 'saga'}, default='lbfgs'

Algorithm to use in the optimization problem. Default is 'lbfgs'.
To choose a solver, you might want to consider the following aspects:

- 'lbfgs' is a good default solver because it works reasonably well for a wide
 class of problems.
- For :term:`multiclass` problems (`n_classes >= 3`), all solvers except
 'liblinear' minimize the full multinomial loss, 'liblinear' will raise an
 error.
- 'newton-cholesky' is a good choice for
 `n_samples` >> `n_features * n_classes`, especially with one-hot encoded
 categorical features with rare categories. Be aware that the memory usage
 of this solver has a quadratic dependency on `n_features * n_classes`
 because it explicitly computes the full Hessian matrix.
- For small datasets, 'liblinear' is a good choice, whereas 'sag'
 and 'saga' are faster for large ones;
- 'liblinear' can only handle binary classification by default. To apply a
 one-versus-rest scheme for the multiclass setting one can wrap it with the
 :class:`~sklearn.multiclass.OneVsRestClassifier`.

.. warning::
 The choice of the algorithm depends on the penalty chosen (`l1_ratio=0`
 for L2-penalty, `l1_ratio=1` for L1-penalty and `0 < l1_ratio < 1` for
 Elastic-Net) and on (multinomial) multiclass support:

 ================= ======================== ======================
 solver l1_ratio multinomial multiclass
 ================= ======================== ======================
 'lbfgs' l1_ratio=0 yes
 'liblinear' l1_ratio=1 or l1_ratio=0 no
 'newton-cg' l1_ratio=0 yes
 'newton-cholesky' l1_ratio=0 yes
 'sag' l1_ratio=0 yes
 'saga' 0<=l1_ratio<=1 yes
 ================= ======================== ======================

.. note::
 'sag' and 'saga' fast convergence is only guaranteed on features
 with approximately the same scale. You can preprocess the data with
 a scaler from :mod:`sklearn.preprocessing`.

.. seealso::
 Refer to the :ref:`User Guide ` for more
 information regarding :class:`LogisticRegression` and more specifically the
 :ref:`Table `
 summarizing solver/penalty supports.

.. versionadded:: 0.17
 Stochastic Average Gradient (SAG) descent solver. Multinomial support in
 version 0.18.
.. versionadded:: 0.19
 SAGA solver.
.. versionchanged:: 0.22
 The default solver changed from 'liblinear' to 'lbfgs' in 0.22.
.. versionadded:: 1.2
 newton-cholesky solver. Multinomial support in version 1.6.

'newton-cg'

 max_iter
 max_iter: int, default=100

Maximum number of iterations taken for the solvers to converge.

100

 verbose
 verbose: int, default=0

For the liblinear and lbfgs solvers set verbose to any positive
number for verbosity.

0

 warm_start
 warm_start: bool, default=False

When set to True, reuse the solution of the previous call to fit as
initialization, otherwise, just erase the previous solution.
Useless for liblinear solver. See :term:`the Glossary `.

.. versionadded:: 0.17
 *warm_start* to support *lbfgs*, *newton-cg*, *sag*, *saga* solvers.

False

 n_jobs
 n_jobs: int, default=None

Does not have any effect.

.. deprecated:: 1.8
 `n_jobs` is deprecated in version 1.8 and will be removed in 1.10.

None

Считаем метрики

In [12]:

y_pred = pipeline.predict(X_test)
y_proba = pipeline.predict_proba(X_test)[:, 1]

metrics = calculate_metrics(y_test, y_pred, y_proba)

In [13]:

print(f"Accuracy: {metrics['accuracy']:.4f}")
print(f"F1-score: {metrics['f1']:.4f}")
print(f"ROC-AUC: {metrics['roc_auc']:.4f}")

Accuracy: 0.8543
F1-score: 0.6683
ROC-AUC: 0.9043

In [14]:

cm_fig, ax = plt.subplots(figsize=(8, 6))
ConfusionMatrixDisplay.from_predictions(y_test, y_pred, ax=ax, cmap='Blues')
plt.title("Confusion Matrix")
plt.show()

Проверял следующие гипотезы:

Влияние коэффициента регуляризации в LogReg.

Влияние методов нормализации признаков в LogReg.

Влияние оптимизаторов в LogReg.

Влияние глубины в DesicionTree.

Влияние количества деревьев в RandomForest.

Влияние способа кодирования категориальных признаков в RF.

In [15]:

for c in [0.01, 0.1, 1, 10]:
 params = dict(penalty='l2', C=c, solver='newton-cg', max_iter=100, random_state=RANDOM_STATE)

 model = LogisticRegression(**params)
 pipeline = Pipeline([('preprocess', preprocessor), ('model', model)])
 pipeline.fit(X_train, y_train)
 push_mlflow_experiment(pipeline, X_test, y_test, "LogisticRegression", params,
 f"LogReg C: {c}", {"scaler": "Standard", "encoder": "OneHot"})

c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\sklearn\linear_model\_logistic.py:1135: FutureWarning: 'penalty' was deprecated in version 1.8 and will be removed in 1.10. To avoid this warning, leave 'penalty' set to its default value and use 'l1_ratio' or 'C' instead. Use l1_ratio=0 instead of penalty='l2', l1_ratio=1 instead of penalty='l1', and C=np.inf instead of penalty=None.
 warnings.warn(
2026/04/24 17:15:36 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Successfully registered model 'ClassificationModel'.
2026/04/24 17:15:37 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 1
Created version '1' of model 'ClassificationModel'.

🏃 View run LogisticRegression_LogReg C: 0.01 at: http://158.160.242.172:5000/#/experiments/23/runs/0c55447fcedb43ec84fefb7981529ec1
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\sklearn\linear_model\_logistic.py:1135: FutureWarning: 'penalty' was deprecated in version 1.8 and will be removed in 1.10. To avoid this warning, leave 'penalty' set to its default value and use 'l1_ratio' or 'C' instead. Use l1_ratio=0 instead of penalty='l2', l1_ratio=1 instead of penalty='l1', and C=np.inf instead of penalty=None.
 warnings.warn(
2026/04/24 17:15:46 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:15:46 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 2
Created version '2' of model 'ClassificationModel'.

🏃 View run LogisticRegression_LogReg C: 0.1 at: http://158.160.242.172:5000/#/experiments/23/runs/24442dc17cf3482b838902a2a05c3cbe
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\sklearn\linear_model\_logistic.py:1135: FutureWarning: 'penalty' was deprecated in version 1.8 and will be removed in 1.10. To avoid this warning, leave 'penalty' set to its default value and use 'l1_ratio' or 'C' instead. Use l1_ratio=0 instead of penalty='l2', l1_ratio=1 instead of penalty='l1', and C=np.inf instead of penalty=None.
 warnings.warn(
2026/04/24 17:15:57 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:15:58 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 3
Created version '3' of model 'ClassificationModel'.

🏃 View run LogisticRegression_LogReg C: 1 at: http://158.160.242.172:5000/#/experiments/23/runs/65669363d0a5456dad01ae652d8a66d0
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\sklearn\linear_model\_logistic.py:1135: FutureWarning: 'penalty' was deprecated in version 1.8 and will be removed in 1.10. To avoid this warning, leave 'penalty' set to its default value and use 'l1_ratio' or 'C' instead. Use l1_ratio=0 instead of penalty='l2', l1_ratio=1 instead of penalty='l1', and C=np.inf instead of penalty=None.
 warnings.warn(
2026/04/24 17:16:14 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:16:15 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 4
Created version '4' of model 'ClassificationModel'.

🏃 View run LogisticRegression_LogReg C: 10 at: http://158.160.242.172:5000/#/experiments/23/runs/ea8e1eac852042ffa63f37d2b24ca980
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

In [ ]:

scalers = [('Standard', StandardScaler()), ('Robust', RobustScaler()), ('MinMax', MinMaxScaler())]
for name, sc in scalers:
 preproc = ColumnTransformer(transformers=[
 ('cat', OneHotEncoder(handle_unknown='ignore'), cat_features),
 ('num', sc, num_features)])
 params = dict(penalty='l2', C=0.1, solver='newton-cg', max_iter=100, random_state=RANDOM_STATE)
 pipeline = Pipeline([('preprocess', preproc), ('model', LogisticRegression(**params))])
 pipeline.fit(X_train, y_train)
 push_mlflow_experiment(pipeline, X_test, y_test, "LogisticRegression", params,
 f"LogReg Scaler: {name}", {"scaler": name, "encoder": "OneHot"})

c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\sklearn\linear_model\_logistic.py:1135: FutureWarning: 'penalty' was deprecated in version 1.8 and will be removed in 1.10. To avoid this warning, leave 'penalty' set to its default value and use 'l1_ratio' or 'C' instead. Use l1_ratio=0 instead of penalty='l2', l1_ratio=1 instead of penalty='l1', and C=np.inf instead of penalty=None.
 warnings.warn(
2026/04/24 17:25:51 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:25:52 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 5
Created version '5' of model 'ClassificationModel'.

🏃 View run LogisticRegression_LogReg Scaler: at: http://158.160.242.172:5000/#/experiments/23/runs/4a6cdc3e0ab342db947bf3320fab7c62
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\sklearn\linear_model\_logistic.py:1135: FutureWarning: 'penalty' was deprecated in version 1.8 and will be removed in 1.10. To avoid this warning, leave 'penalty' set to its default value and use 'l1_ratio' or 'C' instead. Use l1_ratio=0 instead of penalty='l2', l1_ratio=1 instead of penalty='l1', and C=np.inf instead of penalty=None.
 warnings.warn(
2026/04/24 17:26:09 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:26:10 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 6
Created version '6' of model 'ClassificationModel'.

🏃 View run LogisticRegression_LogReg Scaler: at: http://158.160.242.172:5000/#/experiments/23/runs/d693e69e486e42d69fe71609d02d516e
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\sklearn\linear_model\_logistic.py:1135: FutureWarning: 'penalty' was deprecated in version 1.8 and will be removed in 1.10. To avoid this warning, leave 'penalty' set to its default value and use 'l1_ratio' or 'C' instead. Use l1_ratio=0 instead of penalty='l2', l1_ratio=1 instead of penalty='l1', and C=np.inf instead of penalty=None.
 warnings.warn(
2026/04/24 17:26:25 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:26:25 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 7
Created version '7' of model 'ClassificationModel'.

🏃 View run LogisticRegression_LogReg Scaler: at: http://158.160.242.172:5000/#/experiments/23/runs/20a51957cefc486db64f45af65709ca2
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

In [ ]:

preprocessor = ColumnTransformer(transformers=[
 ('cat', OneHotEncoder(handle_unknown='ignore'), cat_features),
 ('num', RobustScaler(), num_features)])

for s in ['newton-cg', 'lbfgs', 'liblinear']:
 params = dict(penalty='l2', C=1.0, solver=s, max_iter=200, random_state=RANDOM_STATE)
 model = LogisticRegression(**params)
 pipeline = Pipeline([('preprocess', preprocessor), ('model', model)])
 pipeline.fit(X_train, y_train)
 push_mlflow_experiment(pipeline, X_test, y_test, "LogisticRegression", params,
 f"Solver: {s}", {"scaler": "Robust", "encoder": "OneHot"})

c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\sklearn\linear_model\_logistic.py:1135: FutureWarning: 'penalty' was deprecated in version 1.8 and will be removed in 1.10. To avoid this warning, leave 'penalty' set to its default value and use 'l1_ratio' or 'C' instead. Use l1_ratio=0 instead of penalty='l2', l1_ratio=1 instead of penalty='l1', and C=np.inf instead of penalty=None.
 warnings.warn(
2026/04/24 17:34:33 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:34:34 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 11
Created version '11' of model 'ClassificationModel'.
c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\sklearn\linear_model\_logistic.py:1135: FutureWarning: 'penalty' was deprecated in version 1.8 and will be removed in 1.10. To avoid this warning, leave 'penalty' set to its default value and use 'l1_ratio' or 'C' instead. Use l1_ratio=0 instead of penalty='l2', l1_ratio=1 instead of penalty='l1', and C=np.inf instead of penalty=None.
 warnings.warn(

🏃 View run LogisticRegression_Solver: newton- at: http://158.160.242.172:5000/#/experiments/23/runs/8c32d6580da34e478a72be8ec70c156f
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\sklearn\linear_model\_logistic.py:406: ConvergenceWarning: lbfgs failed to converge after 200 iteration(s) (status=1):
STOP: TOTAL NO. OF ITERATIONS REACHED LIMIT

Increase the number of iterations to improve the convergence (max_iter=200).
You might also want to scale the data as shown in:
 https://scikit-learn.org/stable/modules/preprocessing.html
Please also refer to the documentation for alternative solver options:
 https://scikit-learn.org/stable/modules/linear_model.html#logistic-regression
 n_iter_i = _check_optimize_result(
2026/04/24 17:34:42 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:34:42 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 12
Created version '12' of model 'ClassificationModel'.

🏃 View run LogisticRegression_Solver: lbfgs at: http://158.160.242.172:5000/#/experiments/23/runs/a38a54c25e0b4854b478ad95e973ce51
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

c:\Users\vhane\AppData\Local\Programs\Python\Python312\Lib\site-packages\sklearn\linear_model\_logistic.py:1135: FutureWarning: 'penalty' was deprecated in version 1.8 and will be removed in 1.10. To avoid this warning, leave 'penalty' set to its default value and use 'l1_ratio' or 'C' instead. Use l1_ratio=0 instead of penalty='l2', l1_ratio=1 instead of penalty='l1', and C=np.inf instead of penalty=None.
 warnings.warn(
2026/04/24 17:34:50 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:34:51 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 13

🏃 View run LogisticRegression_Solver: libline at: http://158.160.242.172:5000/#/experiments/23/runs/8a639d2773054e85a74461839ca64baa
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

Created version '13' of model 'ClassificationModel'.

In [21]:

preprocessor = preprocessor = ColumnTransformer(transformers=[
 ('cat', OneHotEncoder(handle_unknown='ignore'), cat_features),
 ('num', 'passthrough', num_features)])

In [ ]:

for d in [3, 5, 10, 15]:
 params = dict(n_estimators=10, max_depth=d, random_state=RANDOM_STATE)
 model = RandomForestClassifier(**params)
 pipeline = Pipeline([('preprocess', preprocessor), ('model', model)])
 pipeline.fit(X_train, y_train)
 push_mlflow_experiment(pipeline, X_test, y_test, "RandomForest", params,
 f"RF maxdepth: {d}", {"scaler": "None", "encoder": "OneHot"})

2026/04/24 17:51:57 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:51:57 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 18
Created version '18' of model 'ClassificationModel'.

🏃 View run RandomForest_RF maxdepth: 3 at: http://158.160.242.172:5000/#/experiments/23/runs/768d472f1d41424aad5c400da5e47440
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

2026/04/24 17:52:05 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:52:06 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 19
Created version '19' of model 'ClassificationModel'.

🏃 View run RandomForest_RF maxdepth: 5 at: http://158.160.242.172:5000/#/experiments/23/runs/65e082a7dbdc4c71ae2f214c789e5a10
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

2026/04/24 17:52:14 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:52:14 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 20
Created version '20' of model 'ClassificationModel'.

🏃 View run RandomForest_RF maxdepth: 10 at: http://158.160.242.172:5000/#/experiments/23/runs/eba75fb24b96478090c65909933dce8b
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

2026/04/24 17:52:25 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:52:26 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 21

🏃 View run RandomForest_RF maxdepth: 15 at: http://158.160.242.172:5000/#/experiments/23/runs/cc56b83698ac4bad90b351e6cc714288
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

Created version '21' of model 'ClassificationModel'.

In [26]:

for n in [10, 50, 100, 200]:
 params = dict(n_estimators=n, max_depth=15, random_state=RANDOM_STATE)
 model = RandomForestClassifier(**params)
 pipeline = Pipeline([('preprocess', preprocessor), ('model', model)])
 pipeline.fit(X_train, y_train)
 push_mlflow_experiment(pipeline, X_test, y_test, "RandomForest", params,
 f"RF n_est: {n}", {"scaler": "None", "encoder": "OneHot"})

2026/04/24 17:58:13 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:58:13 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 28
Created version '28' of model 'ClassificationModel'.

🏃 View run RandomForest_RF n_est: 10 at: http://158.160.242.172:5000/#/experiments/23/runs/6cc29b8ad665481f9dbe9084a80d8f2a
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

2026/04/24 17:58:25 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:58:26 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 29
Created version '29' of model 'ClassificationModel'.

🏃 View run RandomForest_RF n_est: 50 at: http://158.160.242.172:5000/#/experiments/23/runs/e95f9f8bad87427ca5d093e2691c9162
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

2026/04/24 17:58:45 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:58:48 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 30
Created version '30' of model 'ClassificationModel'.

🏃 View run RandomForest_RF n_est: 100 at: http://158.160.242.172:5000/#/experiments/23/runs/7b3c615465a44b47a09a5f58f2c89d57
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

2026/04/24 17:59:12 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:59:15 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 31

🏃 View run RandomForest_RF n_est: 200 at: http://158.160.242.172:5000/#/experiments/23/runs/037e7b61f3904c0d85687a4b2e3d1d10
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

Created version '31' of model 'ClassificationModel'.

In [ ]:

encoders = [('OneHot', OneHotEncoder(handle_unknown='ignore')),
 ('Ordinal', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1))]
for name, enc in encoders:
 preproc = ColumnTransformer(transformers=[
 ('cat', enc, cat_features),
 ('num', 'passthrough', num_features)])
 params = dict(n_estimators=200, max_depth=15, random_state=RANDOM_STATE)
 pipeline = Pipeline([('preprocess', preproc), ('model', RandomForestClassifier(**params))])
 pipeline.fit(X_train, y_train)
 push_mlflow_experiment(pipeline, X_test, y_test, "RandomForest", params,
 f"Encoder: {name}", {"scaler": "None", "encoder": name})

2026/04/24 17:59:48 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 17:59:53 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 32
Created version '32' of model 'ClassificationModel'.

🏃 View run RandomForest_Encoder: OneHot at: http://158.160.242.172:5000/#/experiments/23/runs/507a7d118f584594af6a66f074bf5bd5
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

2026/04/24 18:00:03 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.
Registered model 'ClassificationModel' already exists. Creating a new version of this model...
2026/04/24 18:00:08 INFO mlflow.store.model_registry.abstract_store: Waiting up to 300 seconds for model version to finish creation. Model name: ClassificationModel, version 33

🏃 View run RandomForest_Encoder: Ordina at: http://158.160.242.172:5000/#/experiments/23/runs/d7b036f1947040eab3d0299d83be3179
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/23

Created version '33' of model 'ClassificationModel'.

Лучшая модель:¶

In [33]:

best_params = dict(n_estimators=200, max_depth=15, random_state=RANDOM_STATE)

best_preprocessor = ColumnTransformer(transformers=[
 ('cat', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1), cat_features),
 ('num', 'passthrough', num_features)])

pipeline = Pipeline([('preprocess', best_preprocessor),
 ('model', RandomForestClassifier(**best_params))])

pipeline.fit(X_train, y_train)
y_pred_final = pipeline.predict(X_test)
y_proba_final = pipeline.predict_proba(X_test)[:, 1]

for name, val in calculate_metrics(y_test, y_pred_final, y_proba_final).items():
 print(f"{name}: {val}")

accuracy: 0.8619683709504069
precision: 0.7762180016515277
recall: 0.5994897959183674
f1: 0.6765023389708529
roc_auc: 0.9131927606735314
pr_auc: 0.8017730117332826
