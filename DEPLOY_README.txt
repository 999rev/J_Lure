Cloudflare Pages 部署步骤（免费 HTTPS + 免代理直连）：

1. 解压本压缩包，确保根目录直接包含 index.html 和 functions/ 文件夹。
2. 登录 Cloudflare 控制台 -> Workers & Pages -> Create -> Pages -> Upload assets（或连接 GitHub 仓库）。
3. 填入项目名称（如 castwindow-gx），直接把解压后的文件夹拖进去上传并点击 Deploy site。
4. 部署完成后会得到一个 https://xxx.pages.dev 网址，用手机系统浏览器打开即可一键 GPS 定位并直连实时气象。
