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
    status.textContent = '本地服务已连接'
    port.textContent = r.data.version ? `v${r.data.version}` : ''
  } else {
    card.classList.add('bad')
    card.classList.remove('ok')
    status.textContent = '本地服务未连接'
    port.textContent = '启动后台后刷新'
  }
})

refresh()
