# 手机私有部署

状态：已准备云端入口与手机布局，尚未上传或部署。不得将本机网址当公网地址。

1. 在自己的 GitHub 账号新建 **Private** 仓库 investment-ai，上传本项目代码和两份观察名单。
2. 在 Streamlit Community Cloud 关联该私有仓库，入口选择 `cloud_app.py`，Python 选择 3.12。
3. 应用访问权限保持 **Private**，仅保留自己的访问权限，不改为公开。
4. 部署后验证登录限制：未登录不得看到名单。登录后核对50股/20股、搜索、排序和刷新。
5. 在手机浏览器打开部署成功后的 HTTPS 网址。默认手机简洁布局，完整行情可横滑，诊断在下方，也可下拉选择股票详情。

云端入口关闭名单编辑和本地文档展示；行情缓存属于临时数据，重启后可重新获取。名单变更从本地修改后提交到私有仓库。只读模式不等于登录保护，必须设置平台私有访问。

不会上传虚拟环境、行情缓存、报告、日志或 secrets.toml。首次云端运行没有报价缓存，需刷新；数据源在云端是否可达必须部署后实测。今日净流入仍无可靠来源，不能承诺部署会解决代理或数据源问题。

官方说明：
- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app

本地运行仍用 `python -m streamlit run app.py`。云端入口可用 `python -m streamlit run cloud_app.py` 测试。
