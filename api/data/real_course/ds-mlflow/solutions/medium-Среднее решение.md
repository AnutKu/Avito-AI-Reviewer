<!-- Извлечено из Product-part/01_Входящие/homework_examples/data_science/Пример домашки 1. (АА)/Среднее решение.html скриптом api/scripts/extract_homework.py. Не редактировать вручную. -->

tracking_hw_best_models

Ноутбук для семинара Трекинг экспериментов¶

Сегодня мы:

рассмотрим пайплайн подготовки данных и обучения модели классификации доходов

создадим эксперимент в MLflow и настроим логирование:
параметров

метрик

моделей

артефактов

проведём серию запусков с изменением параметров и сравним результаты в UI MLflow

In [1]:

!pip install numpy datasets scikit-learn mlflow==2.20.2

Requirement already satisfied: numpy in /usr/local/lib/python3.12/dist-packages (2.0.2)
Requirement already satisfied: datasets in /usr/local/lib/python3.12/dist-packages (4.0.0)
Requirement already satisfied: scikit-learn in /usr/local/lib/python3.12/dist-packages (1.6.1)
Requirement already satisfied: mlflow==2.20.2 in /usr/local/lib/python3.12/dist-packages (2.20.2)
Requirement already satisfied: mlflow-skinny==2.20.2 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (2.20.2)
Requirement already satisfied: Flask<4 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (3.1.3)
Requirement already satisfied: Jinja2<4,>=2.11 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (3.1.6)
Requirement already satisfied: alembic!=1.10.0,<2 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (1.18.4)
Requirement already satisfied: docker<8,>=4.0.0 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (7.1.0)
Requirement already satisfied: graphene<4 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (3.4.3)
Requirement already satisfied: gunicorn<24 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (23.0.0)
Requirement already satisfied: markdown<4,>=3.3 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (3.10.2)
Requirement already satisfied: matplotlib<4 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (3.10.0)
Requirement already satisfied: pandas<3 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (2.2.2)
Requirement already satisfied: pyarrow<19,>=4.0.0 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (18.1.0)
Requirement already satisfied: scipy<2 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (1.16.3)
Requirement already satisfied: sqlalchemy<3,>=1.4.0 in /usr/local/lib/python3.12/dist-packages (from mlflow==2.20.2) (2.0.49)
Requirement already satisfied: cachetools<6,>=5.0.0 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (5.5.2)
Requirement already satisfied: click<9,>=7.0 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (8.3.2)
Requirement already satisfied: cloudpickle<4 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (3.1.2)
Requirement already satisfied: databricks-sdk<1,>=0.20.0 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (0.103.0)
Requirement already satisfied: gitpython<4,>=3.1.9 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (3.1.46)
Requirement already satisfied: importlib_metadata!=4.7.0,<9,>=3.7.0 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (8.7.1)
Requirement already satisfied: opentelemetry-api<3,>=1.9.0 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (1.38.0)
Requirement already satisfied: opentelemetry-sdk<3,>=1.9.0 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (1.38.0)
Requirement already satisfied: packaging<25 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (24.2)
Requirement already satisfied: protobuf<6,>=3.12.0 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (5.29.6)
Requirement already satisfied: pydantic<3,>=1.10.8 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (2.12.3)
Requirement already satisfied: pyyaml<7,>=5.1 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (6.0.3)
Requirement already satisfied: requests<3,>=2.17.3 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (2.32.4)
Requirement already satisfied: sqlparse<1,>=0.4.0 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (0.5.5)
Requirement already satisfied: typing-extensions<5,>=4.0.0 in /usr/local/lib/python3.12/dist-packages (from mlflow-skinny==2.20.2->mlflow==2.20.2) (4.15.0)
Requirement already satisfied: filelock in /usr/local/lib/python3.12/dist-packages (from datasets) (3.25.2)
Requirement already satisfied: dill<0.3.9,>=0.3.0 in /usr/local/lib/python3.12/dist-packages (from datasets) (0.3.8)
Requirement already satisfied: tqdm>=4.66.3 in /usr/local/lib/python3.12/dist-packages (from datasets) (4.67.3)
Requirement already satisfied: xxhash in /usr/local/lib/python3.12/dist-packages (from datasets) (3.6.0)
Requirement already satisfied: multiprocess<0.70.17 in /usr/local/lib/python3.12/dist-packages (from datasets) (0.70.16)
Requirement already satisfied: fsspec<=2025.3.0,>=2023.1.0 in /usr/local/lib/python3.12/dist-packages (from fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (2025.3.0)
Requirement already satisfied: huggingface-hub>=0.24.0 in /usr/local/lib/python3.12/dist-packages (from datasets) (1.10.1)
Requirement already satisfied: joblib>=1.2.0 in /usr/local/lib/python3.12/dist-packages (from scikit-learn) (1.5.3)
Requirement already satisfied: threadpoolctl>=3.1.0 in /usr/local/lib/python3.12/dist-packages (from scikit-learn) (3.6.0)
Requirement already satisfied: Mako in /usr/local/lib/python3.12/dist-packages (from alembic!=1.10.0,<2->mlflow==2.20.2) (1.3.10)
Requirement already satisfied: urllib3>=1.26.0 in /usr/local/lib/python3.12/dist-packages (from docker<8,>=4.0.0->mlflow==2.20.2) (2.5.0)
Requirement already satisfied: blinker>=1.9.0 in /usr/local/lib/python3.12/dist-packages (from Flask<4->mlflow==2.20.2) (1.9.0)
Requirement already satisfied: itsdangerous>=2.2.0 in /usr/local/lib/python3.12/dist-packages (from Flask<4->mlflow==2.20.2) (2.2.0)
Requirement already satisfied: markupsafe>=2.1.1 in /usr/local/lib/python3.12/dist-packages (from Flask<4->mlflow==2.20.2) (3.0.3)
Requirement already satisfied: werkzeug>=3.1.0 in /usr/local/lib/python3.12/dist-packages (from Flask<4->mlflow==2.20.2) (3.1.8)
Requirement already satisfied: aiohttp!=4.0.0a0,!=4.0.0a1 in /usr/local/lib/python3.12/dist-packages (from fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (3.13.5)
Requirement already satisfied: graphql-core<3.3,>=3.1 in /usr/local/lib/python3.12/dist-packages (from graphene<4->mlflow==2.20.2) (3.2.8)
Requirement already satisfied: graphql-relay<3.3,>=3.1 in /usr/local/lib/python3.12/dist-packages (from graphene<4->mlflow==2.20.2) (3.2.0)
Requirement already satisfied: python-dateutil<3,>=2.7.0 in /usr/local/lib/python3.12/dist-packages (from graphene<4->mlflow==2.20.2) (2.9.0.post0)
Requirement already satisfied: hf-xet<2.0.0,>=1.4.3 in /usr/local/lib/python3.12/dist-packages (from huggingface-hub>=0.24.0->datasets) (1.4.3)
Requirement already satisfied: httpx<1,>=0.23.0 in /usr/local/lib/python3.12/dist-packages (from huggingface-hub>=0.24.0->datasets) (0.28.1)
Requirement already satisfied: typer in /usr/local/lib/python3.12/dist-packages (from huggingface-hub>=0.24.0->datasets) (0.24.1)
Requirement already satisfied: contourpy>=1.0.1 in /usr/local/lib/python3.12/dist-packages (from matplotlib<4->mlflow==2.20.2) (1.3.3)
Requirement already satisfied: cycler>=0.10 in /usr/local/lib/python3.12/dist-packages (from matplotlib<4->mlflow==2.20.2) (0.12.1)
Requirement already satisfied: fonttools>=4.22.0 in /usr/local/lib/python3.12/dist-packages (from matplotlib<4->mlflow==2.20.2) (4.62.1)
Requirement already satisfied: kiwisolver>=1.3.1 in /usr/local/lib/python3.12/dist-packages (from matplotlib<4->mlflow==2.20.2) (1.5.0)
Requirement already satisfied: pillow>=8 in /usr/local/lib/python3.12/dist-packages (from matplotlib<4->mlflow==2.20.2) (11.3.0)
Requirement already satisfied: pyparsing>=2.3.1 in /usr/local/lib/python3.12/dist-packages (from matplotlib<4->mlflow==2.20.2) (3.3.2)
Requirement already satisfied: pytz>=2020.1 in /usr/local/lib/python3.12/dist-packages (from pandas<3->mlflow==2.20.2) (2025.2)
Requirement already satisfied: tzdata>=2022.7 in /usr/local/lib/python3.12/dist-packages (from pandas<3->mlflow==2.20.2) (2026.1)
Requirement already satisfied: charset_normalizer<4,>=2 in /usr/local/lib/python3.12/dist-packages (from requests<3,>=2.17.3->mlflow-skinny==2.20.2->mlflow==2.20.2) (3.4.7)
Requirement already satisfied: idna<4,>=2.5 in /usr/local/lib/python3.12/dist-packages (from requests<3,>=2.17.3->mlflow-skinny==2.20.2->mlflow==2.20.2) (3.11)
Requirement already satisfied: certifi>=2017.4.17 in /usr/local/lib/python3.12/dist-packages (from requests<3,>=2.17.3->mlflow-skinny==2.20.2->mlflow==2.20.2) (2026.2.25)
Requirement already satisfied: greenlet>=1 in /usr/local/lib/python3.12/dist-packages (from sqlalchemy<3,>=1.4.0->mlflow==2.20.2) (3.4.0)
Requirement already satisfied: aiohappyeyeballs>=2.5.0 in /usr/local/lib/python3.12/dist-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (2.6.1)
Requirement already satisfied: aiosignal>=1.4.0 in /usr/local/lib/python3.12/dist-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (1.4.0)
Requirement already satisfied: attrs>=17.3.0 in /usr/local/lib/python3.12/dist-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (26.1.0)
Requirement already satisfied: frozenlist>=1.1.1 in /usr/local/lib/python3.12/dist-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (1.8.0)
Requirement already satisfied: multidict<7.0,>=4.5 in /usr/local/lib/python3.12/dist-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (6.7.1)
Requirement already satisfied: propcache>=0.2.0 in /usr/local/lib/python3.12/dist-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (0.4.1)
Requirement already satisfied: yarl<2.0,>=1.17.0 in /usr/local/lib/python3.12/dist-packages (from aiohttp!=4.0.0a0,!=4.0.0a1->fsspec[http]<=2025.3.0,>=2023.1.0->datasets) (1.23.0)
Requirement already satisfied: google-auth~=2.0 in /usr/local/lib/python3.12/dist-packages (from databricks-sdk<1,>=0.20.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (2.47.0)
Requirement already satisfied: gitdb<5,>=4.0.1 in /usr/local/lib/python3.12/dist-packages (from gitpython<4,>=3.1.9->mlflow-skinny==2.20.2->mlflow==2.20.2) (4.0.12)
Requirement already satisfied: anyio in /usr/local/lib/python3.12/dist-packages (from httpx<1,>=0.23.0->huggingface-hub>=0.24.0->datasets) (4.13.0)
Requirement already satisfied: httpcore==1.* in /usr/local/lib/python3.12/dist-packages (from httpx<1,>=0.23.0->huggingface-hub>=0.24.0->datasets) (1.0.9)
Requirement already satisfied: h11>=0.16 in /usr/local/lib/python3.12/dist-packages (from httpcore==1.*->httpx<1,>=0.23.0->huggingface-hub>=0.24.0->datasets) (0.16.0)
Requirement already satisfied: zipp>=3.20 in /usr/local/lib/python3.12/dist-packages (from importlib_metadata!=4.7.0,<9,>=3.7.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (3.23.0)
Requirement already satisfied: opentelemetry-semantic-conventions==0.59b0 in /usr/local/lib/python3.12/dist-packages (from opentelemetry-sdk<3,>=1.9.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (0.59b0)
Requirement already satisfied: annotated-types>=0.6.0 in /usr/local/lib/python3.12/dist-packages (from pydantic<3,>=1.10.8->mlflow-skinny==2.20.2->mlflow==2.20.2) (0.7.0)
Requirement already satisfied: pydantic-core==2.41.4 in /usr/local/lib/python3.12/dist-packages (from pydantic<3,>=1.10.8->mlflow-skinny==2.20.2->mlflow==2.20.2) (2.41.4)
Requirement already satisfied: typing-inspection>=0.4.2 in /usr/local/lib/python3.12/dist-packages (from pydantic<3,>=1.10.8->mlflow-skinny==2.20.2->mlflow==2.20.2) (0.4.2)
Requirement already satisfied: six>=1.5 in /usr/local/lib/python3.12/dist-packages (from python-dateutil<3,>=2.7.0->graphene<4->mlflow==2.20.2) (1.17.0)
Requirement already satisfied: shellingham>=1.3.0 in /usr/local/lib/python3.12/dist-packages (from typer->huggingface-hub>=0.24.0->datasets) (1.5.4)
Requirement already satisfied: rich>=12.3.0 in /usr/local/lib/python3.12/dist-packages (from typer->huggingface-hub>=0.24.0->datasets) (13.9.4)
Requirement already satisfied: annotated-doc>=0.0.2 in /usr/local/lib/python3.12/dist-packages (from typer->huggingface-hub>=0.24.0->datasets) (0.0.4)
Requirement already satisfied: smmap<6,>=3.0.1 in /usr/local/lib/python3.12/dist-packages (from gitdb<5,>=4.0.1->gitpython<4,>=3.1.9->mlflow-skinny==2.20.2->mlflow==2.20.2) (5.0.3)
Requirement already satisfied: pyasn1-modules>=0.2.1 in /usr/local/lib/python3.12/dist-packages (from google-auth~=2.0->databricks-sdk<1,>=0.20.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (0.4.2)
Requirement already satisfied: rsa<5,>=3.1.4 in /usr/local/lib/python3.12/dist-packages (from google-auth~=2.0->databricks-sdk<1,>=0.20.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (4.9.1)
Requirement already satisfied: markdown-it-py>=2.2.0 in /usr/local/lib/python3.12/dist-packages (from rich>=12.3.0->typer->huggingface-hub>=0.24.0->datasets) (4.0.0)
Requirement already satisfied: pygments<3.0.0,>=2.13.0 in /usr/local/lib/python3.12/dist-packages (from rich>=12.3.0->typer->huggingface-hub>=0.24.0->datasets) (2.20.0)
Requirement already satisfied: mdurl~=0.1 in /usr/local/lib/python3.12/dist-packages (from markdown-it-py>=2.2.0->rich>=12.3.0->typer->huggingface-hub>=0.24.0->datasets) (0.1.2)
Requirement already satisfied: pyasn1<0.7.0,>=0.6.1 in /usr/local/lib/python3.12/dist-packages (from pyasn1-modules>=0.2.1->google-auth~=2.0->databricks-sdk<1,>=0.20.0->mlflow-skinny==2.20.2->mlflow==2.20.2) (0.6.3)

In [530]:

!pip install catboost -q

 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 97.1/97.1 MB 6.7 MB/s eta 0:00:00

Импорты¶

In [531]:

# импорты для пайплайна

import numpy as np
from datasets import load_dataset
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, precision_score, recall_score, precision_recall_curve, auc
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler, OneHotEncoder, TargetEncoder
import matplotlib.pyplot as plt
import sklearn
import random

import mlflow
from catboost import CatBoostClassifier

In [64]:

dir(sklearn.preprocessing)

Out[64]:

['Binarizer',
 'FunctionTransformer',
 'KBinsDiscretizer',
 'KernelCenterer',
 'LabelBinarizer',
 'LabelEncoder',
 'MaxAbsScaler',
 'MinMaxScaler',
 'MultiLabelBinarizer',
 'Normalizer',
 'OneHotEncoder',
 'OrdinalEncoder',
 'PolynomialFeatures',
 'PowerTransformer',
 'QuantileTransformer',
 'RobustScaler',
 'SplineTransformer',
 'StandardScaler',
 'TargetEncoder',
 '__all__',
 '__builtins__',
 '__cached__',
 '__doc__',
 '__file__',
 '__loader__',
 '__name__',
 '__package__',
 '__path__',
 '__spec__',
 '_csr_polynomial_expansion',
 '_data',
 '_discretization',
 '_encoders',
 '_function_transformer',
 '_label',
 '_polynomial',
 '_target_encoder',
 '_target_encoder_fast',
 'add_dummy_feature',
 'binarize',
 'label_binarize',
 'maxabs_scale',
 'minmax_scale',
 'normalize',
 'power_transform',
 'quantile_transform',
 'robust_scale',
 'scale']

In [4]:

In [65]:

mlflow.set_tracking_uri('http://158.160.242.172:5000/')

In [66]:

mlflow.set_experiment(experiment_id='12')

Out[66]:

<Experiment: artifact_location='mlflow-artifacts:/12', creation_time=1776687378477, experiment_id='12', last_update_time=1776687378477, lifecycle_stage='active', name='homework-eazharikov.ext', tags={}>

Константы¶

In [159]:

DATASET_NAME = 'scikit-learn/adult-census-income'
TEST_SIZE = 0.2
RANDOM_STATE = 42

In [160]:

random.seed(RANDOM_STATE)
np.random.seed(RANDOM_STATE)

Скачивание и подготовка данных¶

Скачаем данные

In [161]:

dataset = load_dataset(DATASET_NAME)

Посмотрим на них и изучим

In [162]:

dataset

Out[162]:

DatasetDict({
 train: Dataset({
 features: ['age', 'workclass', 'fnlwgt', 'education', 'education.num', 'marital.status', 'occupation', 'relationship', 'race', 'sex', 'capital.gain', 'capital.loss', 'hours.per.week', 'native.country', 'income'],
 num_rows: 32561
 })
})

In [163]:

dataset['train'].features

Out[163]:

{'age': Value('int64'),
 'workclass': Value('string'),
 'fnlwgt': Value('int64'),
 'education': Value('string'),
 'education.num': Value('int64'),
 'marital.status': Value('string'),
 'occupation': Value('string'),
 'relationship': Value('string'),
 'race': Value('string'),
 'sex': Value('string'),
 'capital.gain': Value('int64'),
 'capital.loss': Value('int64'),
 'hours.per.week': Value('int64'),
 'native.country': Value('string'),
 'income': Value('string')}

In [280]:

df = dataset['train'].to_pandas()
df

Out[280]:

age
workclass
fnlwgt
education
education.num
marital.status
occupation
relationship
race
sex
capital.gain
capital.loss
hours.per.week
native.country
income

0
90
?
77053
HS-grad
9
Widowed
?
Not-in-family
White
Female
0
4356
40
United-States
<=50K

1
82
Private
132870
HS-grad
9
Widowed
Exec-managerial
Not-in-family
White
Female
0
4356
18
United-States
<=50K

2
66
?
186061
Some-college
10
Widowed
?
Unmarried
Black
Female
0
4356
40
United-States
<=50K

3
54
Private
140359
7th-8th
4
Divorced
Machine-op-inspct
Unmarried
White
Female
0
3900
40
United-States
<=50K

4
41
Private
264663
Some-college
10
Separated
Prof-specialty
Own-child
White
Female
0
3900
40
United-States
<=50K

...

32556
22
Private
310152
Some-college
10
Never-married
Protective-serv
Not-in-family
White
Male
0
40
United-States
<=50K

32557
27
Private
257302
Assoc-acdm
12
Married-civ-spouse
Tech-support
Wife
White
Female
0
38
United-States
<=50K

32558
40
Private
154374
HS-grad
9
Married-civ-spouse
Machine-op-inspct
Husband
White
Male
0
40
United-States
>50K

32559
58
Private
151910
HS-grad
9
Widowed
Adm-clerical
Unmarried
White
Female
0
40
United-States
<=50K

32560
22
Private
201490
HS-grad
9
Never-married
Adm-clerical
Own-child
White
Male
0
20
United-States
<=50K

32561 rows × 15 columns

Описание признаков:

age — возраст человека

workclass — тип занятости

fnlwgt — вес наблюдения в данных переписи населения США (сколько реальных людей в популяции «представляет» эта строка)

education — образование

education.num — уровень образования в виде числа

marital.status — семейное положение

occupation — профессия / род деятельности

relationship — роль человека в семье

race — расовая группа

sex — пол человека (Male / Female)

capital.gain — доход от капитала (прибыль от продажи активов)

capital.loss — убытки от капитала

hours.per.week — количество рабочих часов в неделю

native.country — страна происхождения

Описание таргета:

income — бинарно, получает человек больше 50k $ в год или нет

Оставим только часть признаков

In [447]:

columns = [
 'age', 'workclass', 'education.num', 'occupation', 'marital.status',
 'capital.gain', 'hours.per.week', 'sex',
 'capital.loss', 'native.country', 'race'
]

target_column = 'income'

И разделим датафрейм на признаки и таргет

In [448]:

X, y = df[columns], df[target_column]

In [449]:

X

Out[449]:

age
workclass
education.num
occupation
marital.status
capital.gain
hours.per.week
sex
capital.loss
native.country
race

0
90
?
9
?
Widowed
0
40
Female
4356
United-States
White

1
82
Private
9
Exec-managerial
Widowed
0
18
Female
4356
United-States
White

2
66
?
10
?
Widowed
0
40
Female
4356
United-States
Black

3
54
Private
4
Machine-op-inspct
Divorced
0
40
Female
3900
United-States
White

4
41
Private
10
Prof-specialty
Separated
0
40
Female
3900
United-States
White

...

32556
22
Private
10
Protective-serv
Never-married
0
40
Male
0
United-States
White

32557
27
Private
12
Tech-support
Married-civ-spouse
0
38
Female
0
United-States
White

32558
40
Private
9
Machine-op-inspct
Married-civ-spouse
0
40
Male
0
United-States
White

32559
58
Private
9
Adm-clerical
Widowed
0
40
Female
0
United-States
White

32560
22
Private
9
Adm-clerical
Never-married
0
20
Male
0
United-States
White

32561 rows × 11 columns

In [450]:

y

Out[450]:

income

0
<=50K

1
<=50K

2
<=50K

3
<=50K

4
<=50K

...

32556
<=50K

32557
<=50K

32558
>50K

32559
<=50K

32560
<=50K

32561 rows × 1 columns

dtype: object

Используем Label Encoding для кодирования категориальных признаков

In [451]:

cat_features = [
 'workclass', 'occupation', 'marital.status',
 'sex', 'native.country', 'race'
]
num_features = list(set(columns) - set(cat_features))

In [452]:

preprocessor = ColumnTransformer(
 transformers=[
 # ('cat', OrdinalEncoder(), cat_features),
 ('cat', OneHotEncoder(), cat_features),
 # ('cat', TargetEncoder(), cat_features),
 ('num', StandardScaler(), num_features),
 ]
)

In [453]:

preprocessor

Out[453]:

 ColumnTransformer(transformers=[('cat', OneHotEncoder(),
 ['workclass', 'occupation', 'marital.status',
 'sex', 'native.country', 'race']),
 ('num', StandardScaler(),
 ['education.num', 'capital.loss',
 'capital.gain', 'age', 'hours.per.week'])])
In a Jupyter environment, please rerun this cell to show the HTML representation or trust the notebook.
On GitHub, the HTML representation is unable to render, please try loading this page with nbviewer.org.
ColumnTransformer

?Documentation for ColumnTransformeriNot fitted
ColumnTransformer(transformers=[('cat', OneHotEncoder(),
 ['workclass', 'occupation', 'marital.status',
 'sex', 'native.country', 'race']),
 ('num', StandardScaler(),
 ['education.num', 'capital.loss',
 'capital.gain', 'age', 'hours.per.week'])])

cat

['workclass', 'occupation', 'marital.status', 'sex', 'native.country', 'race']

OneHotEncoder

?Documentation for OneHotEncoder
OneHotEncoder()

num

['education.num', 'capital.loss', 'capital.gain', 'age', 'hours.per.week']

StandardScaler

?Documentation for StandardScaler
StandardScaler()

И закодируем целевую переменную

In [454]:

y.value_counts()

Out[454]:

count

income

<=50K
24720

>50K
7841

dtype: int64

In [455]:

y_transformed = (y == '>50K').astype(int)

In [456]:

y_transformed

Out[456]:

income

0

1
0

2
0

3
0

4
0

...

32556
0

32557
0

32558
1

32559
0

32560
0

32561 rows × 1 columns

dtype: int64

In [457]:

y_transformed.value_counts().plot.bar();

Разделим на train и test

In [459]:

X_train, X_test, y_train, y_test = train_test_split(X, y_transformed, test_size=TEST_SIZE, random_state=RANDOM_STATE)

In [460]:

X_train.shape, X_test.shape, y_train.shape, y_test.shape

Out[460]:

((26048, 11), (6513, 11), (26048,), (6513,))

Обучение модели¶

В качестве бейзлайна возьмём логистическую регрессию

In [514]:

model_params = dict(
 penalty='elasticnet', C=1.5, solver='saga', l1_ratio=0.3, max_iter=10000, random_state=RANDOM_STATE
)
model_params

Out[514]:

{'penalty': 'elasticnet',
 'C': 1.5,
 'solver': 'saga',
 'l1_ratio': 0.3,
 'max_iter': 10000,
 'random_state': 42}

In [515]:

model = LogisticRegression(**model_params, )
model

Out[515]:

 LogisticRegression(C=1.5, l1_ratio=0.3, max_iter=10000, penalty='elasticnet',
 random_state=42, solver='saga')
In a Jupyter environment, please rerun this cell to show the HTML representation or trust the notebook.
On GitHub, the HTML representation is unable to render, please try loading this page with nbviewer.org.
LogisticRegression

?Documentation for LogisticRegressioniNot fitted
LogisticRegression(C=1.5, l1_ratio=0.3, max_iter=10000, penalty='elasticnet',
 random_state=42, solver='saga')

Соберем пайплайн целиком

In [516]:

pipeline = Pipeline([
 ('preprocess', preprocessor),
 ('model', model)
])
pipeline

Out[516]:

 Pipeline(steps=[('preprocess',
 ColumnTransformer(transformers=[('cat', OneHotEncoder(),
 ['workclass', 'occupation',
 'marital.status', 'sex',
 'native.country', 'race']),
 ('num', StandardScaler(),
 ['education.num',
 'capital.loss',
 'capital.gain', 'age',
 'hours.per.week'])])),
 ('model',
 LogisticRegression(C=1.5, l1_ratio=0.3, max_iter=10000,
 penalty='elasticnet', random_state=42,
 solver='saga'))])
In a Jupyter environment, please rerun this cell to show the HTML representation or trust the notebook.
On GitHub, the HTML representation is unable to render, please try loading this page with nbviewer.org.
Pipeline

?Documentation for PipelineiNot fitted
Pipeline(steps=[('preprocess',
 ColumnTransformer(transformers=[('cat', OneHotEncoder(),
 ['workclass', 'occupation',
 'marital.status', 'sex',
 'native.country', 'race']),
 ('num', StandardScaler(),
 ['education.num',
 'capital.loss',
 'capital.gain', 'age',
 'hours.per.week'])])),
 ('model',
 LogisticRegression(C=1.5, l1_ratio=0.3, max_iter=10000,
 penalty='elasticnet', random_state=42,
 solver='saga'))])

preprocess: ColumnTransformer

?Documentation for preprocess: ColumnTransformer
ColumnTransformer(transformers=[('cat', OneHotEncoder(),
 ['workclass', 'occupation', 'marital.status',
 'sex', 'native.country', 'race']),
 ('num', StandardScaler(),
 ['education.num', 'capital.loss',
 'capital.gain', 'age', 'hours.per.week'])])

cat

['workclass', 'occupation', 'marital.status', 'sex', 'native.country', 'race']

OneHotEncoder

?Documentation for OneHotEncoder
OneHotEncoder()

num

['education.num', 'capital.loss', 'capital.gain', 'age', 'hours.per.week']

StandardScaler

?Documentation for StandardScaler
StandardScaler()

LogisticRegression

?Documentation for LogisticRegression
LogisticRegression(C=1.5, l1_ratio=0.3, max_iter=10000, penalty='elasticnet',
 random_state=42, solver='saga')

И запустим обучение

In [517]:

pipeline.fit(X_train, y_train)
pipeline

Out[517]:

 Pipeline(steps=[('preprocess',
 ColumnTransformer(transformers=[('cat', OneHotEncoder(),
 ['workclass', 'occupation',
 'marital.status', 'sex',
 'native.country', 'race']),
 ('num', StandardScaler(),
 ['education.num',
 'capital.loss',
 'capital.gain', 'age',
 'hours.per.week'])])),
 ('model',
 LogisticRegression(C=1.5, l1_ratio=0.3, max_iter=10000,
 penalty='elasticnet', random_state=42,
 solver='saga'))])
In a Jupyter environment, please rerun this cell to show the HTML representation or trust the notebook.
On GitHub, the HTML representation is unable to render, please try loading this page with nbviewer.org.
Pipeline

?Documentation for PipelineiFitted
Pipeline(steps=[('preprocess',
 ColumnTransformer(transformers=[('cat', OneHotEncoder(),
 ['workclass', 'occupation',
 'marital.status', 'sex',
 'native.country', 'race']),
 ('num', StandardScaler(),
 ['education.num',
 'capital.loss',
 'capital.gain', 'age',
 'hours.per.week'])])),
 ('model',
 LogisticRegression(C=1.5, l1_ratio=0.3, max_iter=10000,
 penalty='elasticnet', random_state=42,
 solver='saga'))])

preprocess: ColumnTransformer

?Documentation for preprocess: ColumnTransformer
ColumnTransformer(transformers=[('cat', OneHotEncoder(),
 ['workclass', 'occupation', 'marital.status',
 'sex', 'native.country', 'race']),
 ('num', StandardScaler(),
 ['education.num', 'capital.loss',
 'capital.gain', 'age', 'hours.per.week'])])

cat

['workclass', 'occupation', 'marital.status', 'sex', 'native.country', 'race']

OneHotEncoder

?Documentation for OneHotEncoder
OneHotEncoder()

num

['education.num', 'capital.loss', 'capital.gain', 'age', 'hours.per.week']

StandardScaler

?Documentation for StandardScaler
StandardScaler()

LogisticRegression

?Documentation for LogisticRegression
LogisticRegression(C=1.5, l1_ratio=0.3, max_iter=10000, penalty='elasticnet',
 random_state=42, solver='saga')

Оценка качества модели¶

Получим предсказания на тесте обученной модели

In [547]:

y_proba = pipeline.predict_proba(X_test)[:, 1]

In [548]:

y_proba.shape

Out[548]:

(6513,)

In [549]:

THRESHOLD = 0.6

In [550]:

y_pred = np.where(y_proba >= THRESHOLD, 1, 0)

In [551]:

pipeline.steps[0][1].transformers[0][1]

Out[551]:

 OneHotEncoder()
In a Jupyter environment, please rerun this cell to show the HTML representation or trust the notebook.
On GitHub, the HTML representation is unable to render, please try loading this page with nbviewer.org.
OneHotEncoder

?Documentation for OneHotEncoderiNot fitted
OneHotEncoder()

In [552]:

pipeline.steps[0][1].transformers[1][1]

Out[552]:

 StandardScaler()
In a Jupyter environment, please rerun this cell to show the HTML representation or trust the notebook.
On GitHub, the HTML representation is unable to render, please try loading this page with nbviewer.org.
StandardScaler

?Documentation for StandardScaleriNot fitted
StandardScaler()

Считаем метрики

In [553]:

precision, recall, thresholds = precision_recall_curve(y_test, y_pred)
pr_auc = auc(recall, precision)

plt.figure(figsize=(8, 6))
plt.plot(recall, precision, color='darkorange', lw=2, label=f'PR curve (area = {pr_auc:.2f})')

plt.xlim([0.0, 1.0])
plt.ylim([0.0, 1.05])
plt.xlabel('Recall (Полнота)')
plt.ylabel('Precision (Точность)')
plt.title('Precision-Recall Curve')
plt.legend(loc="lower left")
plt.grid(True)

plt.savefig('pr_curve.png', dpi=300, bbox_inches='tight')
plt.show()

In [554]:

metrics = {
 'accuracy': accuracy_score(y_test, y_pred),
 'precision': precision_score(y_test, y_pred),
 'recall': recall_score(y_test, y_pred),
 'f1': f1_score(y_test, y_pred),
 'roc_auc': roc_auc_score(y_test, y_proba),
 'pr_auc': pr_auc
}

In [555]:

print(f"Accuracy: {metrics['accuracy']:.4f}")
print(f"Precision: {metrics['precision']:.4f}")
print(f"Recall: {metrics['recall']:.4f}")
print(f"F1-score: {metrics['f1']:.4f}")
print(f"ROC-AUC: {metrics['roc_auc']:.7f}")
print(f"PR-AUC: {metrics['pr_auc']:.7f}")

Accuracy: 0.8468
Precision: 0.7770
Recall: 0.4919
F1-score: 0.6024
ROC-AUC: 0.9013172
PR-AUC: 0.6943799

In [513]:

with mlflow.start_run(run_name='logreg_v17'):
 mlflow.log_params(
 {

 'test_size': TEST_SIZE,
 'threshold': THRESHOLD
 }
 )
 mlflow.log_params(model_params)
 mlflow.log_params(
 {
 'cat_features': cat_features,
 'num_features': num_features,
 'cat_preprocessing': type(pipeline.steps[0][1].transformers[0][1]).__name__,
 'num_preprocessing': type(pipeline.steps[0][1].transformers[1][1]).__name__,
 }
 )
 mlflow.log_metrics(metrics)
 mlflow.sklearn.log_model(pipeline, artifact_path='model')
 mlflow.log_artifact('pr_curve.png')

2026/04/20 13:54:41 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.

🏃 View run logreg_v17 at: http://158.160.242.172:5000/#/experiments/12/runs/fe98fa8f474141afa1d59a1860f67e61
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/12

In [ ]:

CATBOOST¶

In [558]:

model_params = {
 'iterations': 10000,
 'learning_rate': 0.01,
 'depth': 7,
 'l2_leaf_reg': 4,
 'random_seed': RANDOM_STATE,
 'verbose': False,
 'early_stopping_rounds': 100,
 'eval_metric': 'AUC'
}

# Создаём модель
model = CatBoostClassifier(**model_params)

# Обучение
model.fit(
 X,
 y,
 cat_features=cat_features,
 verbose=False
)

print("CatBoost успешно обучен с топовыми параметрами!")

CatBoost успешно обучен с топовыми параметрами!

In [559]:

# ==================== Предсказания и метрики для CatBoost ====================

# Получаем вероятности положительного класса
y_proba = model.predict_proba(X_test)[:, 1] # CatBoost возвращает [prob_0, prob_1]

# Бинарные предсказания (по умолчанию порог 0.5)
y_pred = (y_proba >= 0.5).astype(int)

# Расчёт метрик
precision, recall, thresholds = precision_recall_curve(y_test, y_proba)
pr_auc = auc(recall, precision)

# Построение и сохранение PR-кривой
plt.figure(figsize=(8, 6))
plt.plot(recall, precision, color='darkorange', lw=2,
 label=f'PR curve (area = {pr_auc:.4f})')

plt.xlim([0.0, 1.0])
plt.ylim([0.0, 1.05])
plt.xlabel('Recall (Полнота)')
plt.ylabel('Precision (Точность)')
plt.title('Precision-Recall Curve - CatBoost')
plt.legend(loc="lower left")
plt.grid(True)

plt.savefig('pr_curve.png', dpi=300, bbox_inches='tight')
plt.show()

# Метрики
metrics = {
 'accuracy': accuracy_score(y_test, y_pred),
 'precision': precision_score(y_test, y_pred),
 'recall': recall_score(y_test, y_pred),
 'f1': f1_score(y_test, y_pred),
 'roc_auc': roc_auc_score(y_test, y_proba),
 'pr_auc': pr_auc
}

print(f"Accuracy: {metrics['accuracy']:.4f}")
print(f"Precision: {metrics['precision']:.4f}")
print(f"Recall: {metrics['recall']:.4f}")
print(f"F1-score: {metrics['f1']:.4f}")
print(f"ROC-AUC: {metrics['roc_auc']:.4f}")
print(f"PR-AUC: {metrics['pr_auc']:.4f}")

Accuracy: 0.8907
Precision: 0.8235
Recall: 0.6831
F1-score: 0.7468
ROC-AUC: 0.9485
PR-AUC: 0.8673

In [560]:

with mlflow.start_run(run_name='catboost_v4'):
 # Логируем параметры модели
 mlflow.log_params(model_params)

 # Информация о данных и признаках
 mlflow.log_params({
 'num_features': num_features,
 'cat_features': cat_features,
 'model_type': 'CatBoostClassifier',
 'test_size': TEST_SIZE,
 'threshold': 0.5
 })

 # Логируем метрики
 mlflow.log_metrics(metrics)

 # Логируем модель CatBoost
 mlflow.catboost.log_model(model, artifact_path="model")

 # Логируем PR-кривую
 mlflow.log_artifact('pr_curve.png')

 print("✅ CatBoost модель + обновлённая PR-кривая успешно залогированы в MLflow")

2026/04/20 14:57:36 WARNING mlflow.models.model: Model logged without a signature and input example. Please set `input_example` parameter when logging the model to auto infer the model signature.

✅ CatBoost модель + обновлённая PR-кривая успешно залогированы в MLflow
🏃 View run catboost_v4 at: http://158.160.242.172:5000/#/experiments/12/runs/ffc78590e0924ddaa7dc54434fda5f6d
🧪 View experiment at: http://158.160.242.172:5000/#/experiments/12

In [538]:
