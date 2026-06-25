# stick88
这是一个用于YOKOGAWA  DLM3024 的图形化波形保存工具。

## 项目背景（可忽略）

在使用实验室YOKOGAWA DLM3024示波器时，实验流程一般是：

```
开始实验->插U盘->选择路径->更改保存文件名->暂停示波器运行->点击保存->等待进度条跑完->然后点击RUN做下一次实验...
```

等所有的实验都做完后，把U盘从示波器上拔下来，插到电脑上，打开MATLAB分析数据，结果发现——这保存的数据好像有问题啊？为什么还有前几次的实验数据残留？

gg，一天白做（至今没有找出为什么保存的数据会出BUG......感兴趣的同学可以尝试复现一下）

在经历了两次上述操作后，每次实验的流程就变成：

``` 
开始实验->插U盘->选择路径->更改保存文件名->暂停示波器运行->点击保存->等待进度条跑完->拔U盘->把U盘插到电脑上->打开MATLAB->分析观测数据是否有问题->没问题，拔U盘，插U盘，继续实验/有问题，拔U盘，插U盘，重新实验
```

过程似乎有一些太繁琐了，在实验了两三天后便又开始寻找有没有其他从示波器上保存数据的方式——DLM3024可以通过以太网或者USB-B接口与电脑相连。（由于我的电脑没有网口，因此选择了USB-B接口）。

YOKOGAWA的官方文档中，有详细介绍如何通过python与示波器通信并控制示波器。感兴趣的同学可以自行查看官方文档：

```
drivers/tmctl8020/IMB9852UB-01EN.pdf
```

为了优化掉拔插U盘这个步骤，在全程依靠codex下编写了这个项目stick88，以直接将示波器波形保存到电脑上。

## 项目功能

### 1. 图形化保存示波器数据

程序通过 YOKOGAWA TMCTL 与示波器通信。点击“保存数据并绘图”后，程序会向示波器发送 `STOP`。然后读取当前记录中的波形数据，并在保存目录下生成一个以当前时刻命名的文件夹，如"260525_2130"，在文件夹中保存示波器数据。

保存结束后，程序会让示波器退出 remote mode，但不会自动恢复 run 状态，需要手动恢复。

### 2. 自定义保存位置

GUI 左侧可以输入或选择保存目录。

保存目录会记忆到：

```text
stick88_settings.json
```

下次打开程序时会自动显示上一次使用的保存目录。

### 3. 自选保存通道

可以分别勾选：

```text
CH1
CH2
CH3
CH4
```

程序会按照以下固定顺序保存已勾选通道：

```text
CH1 -> CH2 -> CH3 -> CH4
```

每个通道保存为独立 CSV 文件，例如：

```text
CH1.csv
CH2.csv
CH3.csv
CH4.csv
```

实际生成哪些文件取决于 GUI 中勾选了哪些通道。

### 4. 控制保存数据长度

GUI 提供 `1%` 到 `100%` 的滑块和输入框，用于控制保存示波器当前记录长度的比例。

例如示波器完整记录长度为 `1,250,000` 点：

| 保存比例 | 每通道保存点数 |
| -------: | -------------: |
|     100% |      1,250,000 |
|      50% |        625,000 |
|      20% |        250,000 |
|      10% |        125,000 |

注意：当前模式是保存记录开头的前 N% 数据，并不是对完整记录做抽样压缩。

### 5. 自动生成波形图片

程序会读取本次生成的 `CH*.csv`，自动生成一张横向排列的 PNG 图片，以供校对保存的数据是否和示波器显示一致。

GUI 在绘图完毕后会提供可点击链接。点击链接后，会用系统默认图片查看器打开生成的 PNG。

### 6. Markdown 实验记录

GUI 左侧提供 Markdown 文本区。

文本区内容会记忆到：

```text
stick88_settings.json
```

每次保存数据时，程序会把当前 Markdown 内容写入本次数据文件夹：

```text
README.md
```

这样每次波形数据都带有对应的实验说明。

## 快速上手

### 1. 安装运行环境

因为程序使用 64 位 Python 和 `tmctl64.dll`，还需要安装：

```text
Microsoft Visual C++ Redistributable x64
```

除此之外，还需要安装对应的驱动。解压drivers里的` YTUSB2300.zip `文件，运行

```text
Setup.exe
```

### 2. 连接示波器

使用 USB 3.0 A-to-B 线连接电脑和 Yokogawa DLM3024 示波器。

*  USB 3.0 A-to-B 线比较少见，其中一端是USB-B口，一端是USB-A口，且两口都是蓝色的（黑色一般为USB 2.0接口），可以在购物平台上搜“USB3.0打印机线”。

如果是新电脑第一次连接，请确认 Windows 能识别 Yokogawa USBTMC 设备。如果无法识别，优先安装：

```text
drivers\YTUSB2300.zip
```

### 3. 启动程序

推荐直接双击发行版本：

```text
release\stick88_v1.1.0.exe
```

开发时也可以在 `stick88` 文件夹打开 PowerShell 后运行源码：

```powershell
python -u .\src\stick88_scope_app.py
```

### 4. 保存一次数据

基本流程：

1. 打开 GUI。
2. 选择保存位置。
3. 勾选需要保存的通道。
4. 设置保存数据长度比例。
5. 在 Markdown 文本区填写实验说明。
6. 点击“保存数据并绘图”。
7. 等待状态显示“数据已保存完毕”。
8. 点击右侧波形图片链接查看 PNG。

每次保存后，会在保存目录下生成一个以时间命名的文件夹，里面通常包括：

```text
CH1.csv
CH2.csv
CH3.csv
CH4.csv
xxxx.png
README.md
```

实际生成哪些 `CH*.csv`，取决于 GUI 中勾选了哪些通道。

### 5. 移植说明

复制整个 `stick88` 文件夹到其他电脑即可。代码中不包含个人电脑绝对路径；除用户在 GUI 中选择的保存目录会写入 `stick88_settings.json` 外，其余路径均基于 `stick88` 文件夹自身定位。

新电脑首次使用时，通常只需要做三件事：

1. 安装 64 位 Python 和 Python 依赖。
2. 安装 Microsoft Visual C++ Redistributable x64。
3. 如有需要，安装 `drivers\YTUSB2300.zip` 中的 Yokogawa USB 驱动。

## 文件夹结构

建议直接复制并保留整个 `stick88` 文件夹。核心结构如下：

```text
stick88
├─ src
│  ├─ stick88_scope_app.py
│  ├─ save_dlm3024_waveform_csv.py
│  ├─ plot_saved_waveforms_png.py
│  └─ waveform_config.py
├─ drivers
│  ├─ tmctl8020
│  ├─ tmctl8020.zip
│  └─ YTUSB2300.zip
├─ build_specs
│  └─ stick88_v1.1.0.spec
├─ release
│  ├─ stick88_v1.0.0.exe
│  ├─ stick88_v1.0.1.exe
│  ├─ stick88_v1.1.0.exe
│  └─ stick88_settings.json
└─ README.md
```

其中：

- `src`：可维护的 Python 源码，后续版本应从这里修改。
- `drivers/tmctl8020`：PyInstaller 打包时嵌入程序的 Yokogawa TMCTL 文件。
- `drivers`：移植到新电脑时可能用到的安装包。
- `build_specs`：PyInstaller 构建配置。
- `release`：可直接运行和对外发布的版本。

在 `build_specs` 目录下重新构建 v1.1.0：

```powershell
python -m PyInstaller --noconfirm --clean .\stick88_v1.1.0.spec
```

`drivers` 中当前包含：

```text
tmctl8020.zip
YTUSB2300.zip
```

用途：

- `tmctl8020.zip`：Yokogawa TMCTL 通信库安装包。
- `YTUSB2300.zip`：Yokogawa USB/USBTMC 驱动安装包。

如果新电脑无法识别示波器，或程序搜索不到 USBTMC 设备，可以解压并安装 `drivers\YTUSB2300.zip` 中的驱动，优先安装`x64`版本。
