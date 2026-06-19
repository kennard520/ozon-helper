const $ = (id) => document.getElementById(id)

function render(loggedIn, user) {
  $('login-box').classList.toggle('hidden', loggedIn)
  $('user-box').classList.toggle('hidden', !loggedIn)
  if (loggedIn && user) $('who').textContent = '已登录：' + (user.username || '')
}

async function refresh() {
  const r = await OzonHelperBridge.bgCall('authStatus')
  const d = (r && r.data) || {}
  render(!!d.loggedIn, d.user)
}

$('login-btn').addEventListener('click', async () => {
  const username = $('username').value.trim()
  const password = $('password').value
  $('login-err').classList.add('hidden')
  if (!username || !password) {
    $('login-err').textContent = '请输入用户名和密码'
    $('login-err').classList.remove('hidden')
    return
  }
  const r = await OzonHelperBridge.bgCall('login', { username, password })
  if (r && r.ok) {
    $('password').value = ''
    render(true, r.data && r.data.user)
  } else {
    $('login-err').textContent = (r && r.error) || '登录失败'
    $('login-err').classList.remove('hidden')
  }
})

$('logout-btn').addEventListener('click', async () => {
  await OzonHelperBridge.bgCall('logout')
  render(false, null)
})

$('open-admin').addEventListener('click', () => {
  OzonHelperBridge.bgCall('openAdmin')
})

OzonHelperBridge.bgCall('ping').then((r) => {
  const card = $('bk-card')
  const status = $('bk-status')
  const port = $('bk-port')
  if (!status || !card) return
  if (r && r.ok && r.data && r.data.ok) {
    card.classList.add('ok')
    card.classList.remove('bad')
    status.textContent = '后端已连接'
    port.textContent = r.data.version ? `v${r.data.version}` : ''
  } else {
    card.classList.add('bad')
    card.classList.remove('ok')
    status.textContent = '后端未连接'
    port.textContent = '检查网络/地址后刷新'
  }
})

// 开发者：自定义后端地址（留空=用写死的生产服务器）
async function loadBackend() {
  try {
    const st = await chrome.storage.local.get('ozon_backend_base')
    if ($('backend-base')) $('backend-base').value = (st && st.ozon_backend_base) || ''
  } catch (e) {
    /* ignore */
  }
}
$('backend-save').addEventListener('click', async () => {
  const v = $('backend-base').value.trim().replace(/\/+$/, '')
  if (v) {
    await chrome.storage.local.set({ ozon_backend_base: v })
  } else {
    await chrome.storage.local.remove('ozon_backend_base')
  }
  location.reload()
})
$('backend-clear').addEventListener('click', async () => {
  await chrome.storage.local.remove('ozon_backend_base')
  location.reload()
})

loadBackend()
refresh()
