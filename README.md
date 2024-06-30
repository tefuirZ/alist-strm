# alist-strm

本脚本是用来免挂载进行批量创建strm文件供emby、jellyfin等流媒体服务器使用的一个私人化脚本。

脚本使用展示：

![image-20240411060618584](https://drive.tefuir0829.cn/d/yyds/img/1/66170d5ef341e.png)



![cf42d3558cfb0ec99c7737aab0965624](https://drive.tefuir0829.cn/d/yyds/img/1/661713cf90fb1.png)

![image-20240411063503148](https://drive.tefuir0829.cn/d/yyds/img/1/66171418c8aee.png)



# alist-strm脚本webUI版本
（将alist的视频文件生成媒体播放设备可播放的strm文件脚本（带webUI界面））
##  更新日志：

1. 增加配置文件管理webUI管理界面

2. 增加定时任务配置

3. 支持多线程运行，选择配置文件运行多线程运行

4. 优化代码结构

5. 弃用.ini方式的配置文件存储方式，更改为轻量级数据库SQLlite

6. 简化docker配置方法 只需要映射一个端口和一个存放的路径即可

7. 新增文件对比功能（beat）

8. 增加复制配置功能

9. 增加字幕下载功能

##  部署

###  docker一键部署

#### 命令行版本：

```shell
docker run -d --name alist-strm -p 18080:5000 -v /home:/home itefuir/alist-strm:latest

#18080是宿主机端口 不是一定要这个 容器端口5000是一定要的
#/home是本地路径
```

#### docker-compose.yaml配置

```yaml
version: "3"
services:
    alist-strm:
        stdin_open: true
        tty: true
        volumes:
            #跟命令行一样的 前面是宿主机的目录
            - /volume1/video:/volume1/video
        ports:
        	#:前面是宿主机的端口，自由选择
            - "15000:5000"
        environment:
            - TIMEZONE=Asia/Shanghai
        container_name: alist-strm
        #restart: always
        image: itefuir/alist-strm:latest
        network_mode: bridge
```

###   拉取docker镜像网络原因看这里

如果本地镜像拉取困难的可以前往镜像包下载地址下载后导入：[传送门](https://drive.tefuir0829.cn/d/tianyi-geren1/ruanjian/alist-strm.tar)

导入方式就去百度啦 这里就不说啦

##  常见问题

##### 配置格式是什么

运行起来之后他会有个默认配置。如果不会填可以参考默认配置填入配置

![image-20240628213845478](https://drive.tefuir0829.cn/d/yyds/img/1/667ebce4d7a46.png)

配置名称随意修改，其中需要注意的是 忽略目录是必填的，不知道填啥的可以直接填入`/1` 而后更新即可 如果是新建的同理。

##### `alist`令牌如何获取：

```
进入alist网页端，使用管理员账号密码登陆至后台
点击设置后
	点击其他
就可以看到令牌啦
```

![image-20240628214258701](https://drive.tefuir0829.cn/d/yyds/img/1/667ebde1d9178.png)

#####  关于定时任务

定时任务选择需要进行定时的任务，在corn表达式中添加你想要的间隔时间。不会填写corn的可以参考

```
每个字段的取值范围和允许的特殊字符如下：

秒 (秒 可选，在某些系统或应用中才支持): 0-59
分钟: 0-59
小时: 0-23
日期: 1-31 （注意一些月份没有31日）
月份: 1-12 或 JAN-DEC
星期: 0-6 或 SUN-SAT，其中0和7都代表周日
（对于不包括秒的cron表达式，则从分钟开始）
Cron表达式中的特殊字符含义：

*：代表任何可能的值，例如在分钟字段表示每分钟。
,：用于指定多个值，比如 MON,WED,FRI 表示周一、周三和周五。
-：表示范围，如 1-5 表示1到5之间的所有数字。
/：用于指定间隔频率，如 0/15 在分钟字段表示每15分钟执行一次。
示例
每天凌晨1点执行：0 1 * * *
每周一到周五的上午9:30执行：30 9 * * 1-5
每隔5分钟执行一次：*/5 * * * *
每月1号和15号的下午2点执行：0 14 1,15 * *
如果需要包含秒，表达式变为7个字段，第一个字段表示秒，其余相同，例如：

每隔10秒执行一次：*/10 * * * * *
```

此信息来自于大模型AI。 填入之后只有到你设定的那个时间他才会自动运行 可以看定时任务的日志查看是否运行了

#####   关于多线程运行

本脚本先前都是用的单线程多配置文件的方式运行的，如果alist上的资源较多的话可能会造成等待时间过长等等。如果alist是上了cdn或者防火墙的建议将运行本脚本的ip加入白名单以免请求过快触发阈值。

现在是你只要勾选了配置文件并且点击运行（或定时任务设定）它就会自动以每个配置文件为一个线程进行创建strm文件。
