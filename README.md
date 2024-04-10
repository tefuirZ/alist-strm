# alist-strm

本脚本是用来免挂载进行批量创建strm文件供emby、jellyfin等流媒体服务器使用的一个私人化脚本。

脚本使用展示：

![image-20240411060618584](https://drive.tefuir0829.cn/d/yyds/img/1/66170d5ef341e.png)



![cf42d3558cfb0ec99c7737aab0965624](https://drive.tefuir0829.cn/d/yyds/img/1/661713cf90fb1.png)

![image-20240411063503148](https://drive.tefuir0829.cn/d/yyds/img/1/66171418c8aee.png)

食用方式：

```
#因为脚本是使用Python写的，所以一定要有Python环境。版本不需要多高，实测3.11也可以正常运行。
```

[github链接](https://github.com/tefuirZ/alist-strm)

[脚本地址]([raw.githubusercontent.com/tefuirZ/alist-strm/main/main.py](https://raw.githubusercontent.com/tefuirZ/alist-strm/main/main.py))

注：仅脚本单体会报错，所以需要把config.ini一起下载或者自建一个。

```ini
config.ini文件示例:

[DEFAULT]
RootPath = /yyds
#alist路径，即为脚本开始路径
SiteUrl = https://wwww.tefuir0829.cn
#alist地址，注意一定不要带/
TargetDirectory = /home/tefuir
#目标路径
Username = admin
#alist账号
Password = tefuir
#alist密码

#Python脚本是比较注意这些缩进的，还有需要特别注意的就是/斜杠  有些地方斜杠不能丢 有些不能有，有了就报错了
```



Python无非就是模块问题，群辉的话直接使用套件安装Python3.0以上版本。安装完进入ssh使用命令安装模块，

```sh
sudo python3.11 -m pip install requests（目前好像也就这个模块没有，如果有的话换一下模块名一样的。看报错）
```

Linux系统下因为很多环境很复杂，而本脚本也不是长期需要使用，推荐使用Python的虚拟环境直接运行。

```sh
安装Python:
首先检查系统中是否已经安装了Python。在终端中输入以下命令：

python --version
如果没有安装Python或者需要安装新的版本，可以按照以下步骤继续。

使用包管理器安装Python。在大多数Linux发行版中，可以使用以下命令安装Python：

对于 Ubuntu 或 Debian 等基于 apt 的系统：

sudo apt update
sudo apt install python3
对于 CentOS 或 Fedora 等基于 yum 的系统：

sudo yum install python3
创建和运行Python虚拟环境：
安装 virtualenv （如果尚未安装）：

sudo apt install python3-venv   # 对于 Debian/Ubuntu
sudo yum install python3-virtualenv  # 对于 CentOS/Fedora
创建一个新的虚拟环境：

python3 -m venv myenv
这将在当前目录中创建一个名为 myenv 的新虚拟环境。

激活虚拟环境：

source myenv/bin/activate
一旦激活虚拟环境，你会注意到终端提示符前面会显示虚拟环境的名称。

在虚拟环境中安装依赖包或运行Python脚本：

pip install package_name
python your_script.py
退出虚拟环境：

deactivate

###这段直接复制ChatGPT的回答的，大佬们勿喷。。。。。。
```



Windows下食用：

Windows下食用其实也还好，按照百度上的教程把Python装上之后，也是同样的道理安装模块。模块安装完之后修改配置文件，然后就可以运行了。

下面是来着ChatGPT的回答

```shell
在Windows系统下安装Python或者运行Python虚拟环境可以按照以下步骤进行：

### 安装Python:

1. 下载Python安装程序：
   
   访问 Python 官方网站（https://www.python.org/downloads/）下载最新版本的 Python 安装程序（通常是 .exe 文件）。

2. 运行安装程序：
   
   - 双击下载的 Python 安装程序。
   - 在安装向导中选择 "Add Python x.x to PATH" 选项，这样可以在命令提示符中直接运行 Python。
   - 点击 "Install Now" 完成安装。

3. 验证安装：
   
   打开命令提示符（Win + R，输入 `cmd` 回车），输入以下命令来验证 Python 是否成功安装：
   
   ```bash
   python --version
   ```

### 创建和运行Python虚拟环境：

1. 安装 `virtualenv` （如果尚未安装）：

   在命令提示符中运行以下命令：

   ```bash
   pip install virtualenv
   ```

2. 创建一个新的虚拟环境：

   在命令提示符中运行以下命令：

   ```bash
   virtualenv myenv
   ```

   这将在当前目录中创建一个名为 `myenv` 的新虚拟环境。

3. 激活虚拟环境：

   在命令提示符中运行以下命令：

   ```bash
   myenv\Scripts\activate
   ```

   一旦激活虚拟环境，你会注意到命令提示符前面会显示虚拟环境的名称。

4. 在虚拟环境中安装依赖包或运行Python脚本：

   在激活的虚拟环境中，你可以使用 `pip` 安装依赖包或者运行 Python 脚本。

5. 退出虚拟环境：

   在命令提示符中运行以下命令来退出虚拟环境：

   ```bash
   deactivate
   ```

这些是在 Windows 系统下安装 Python 或者运行 Python 虚拟环境的基本步骤。希望这些指导可以帮助你顺利在 Windows 系统中使用
```



目前已知问题：

- 如果alist的原路径有中文的话，会导致一些情况下流媒体服务器播放不出来的情况。

- 无法自动识别ISO文件
- 暂时无法处理图片以及nfo文件
