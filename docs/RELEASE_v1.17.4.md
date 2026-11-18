# TargetForge v1.17.4 更新说明

## 系统代理精确还原

- 修复 `gflh.py` 抓包停止时只执行 `ProxyEnable=0` 的问题；
- 抓包开始前保存完整原值：
  - `ProxyEnable`
  - `ProxyServer`
  - `ProxyOverride`
  - `AutoConfigURL`
- 抓包停止/失败/正常退出时精确还原，不再把 Dove、Clash 等原代理地址覆盖成 `127.0.0.1:18080`；
- 没有抓包前备份时，不再盲目关闭当前系统代理；
- 新增 `tests/test_sysproxy.py` 回归测试。

## 说明

此前 `capture_stop()` 会留下：

```text
ProxyEnable=0
ProxyServer=127.0.0.1:18080
```

用户原本的 `ProxyServer=127.0.0.1:17897` 会丢失；现在会原样恢复。
