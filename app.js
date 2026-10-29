const message = document.querySelector('#message');
const confirmWrites = document.querySelector('#confirm');
const send = document.querySelector('#send');
const answer = document.querySelector('#answer');
const tools = document.querySelector('#tools');

async function ask() {
  const text = message.value.trim();
  if (!text) return;
  send.disabled = true;
  answer.classList.remove('error');
  answer.textContent = 'جارٍ تجهيز الإجابة…';
  tools.textContent = '';
  try {
    const response = await fetch('/api/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text, confirm_writes: confirmWrites.checked})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'تعذر تشغيل الطلب');
    answer.textContent = data.answer;
    tools.textContent = data.tools.length ? `الأدوات المستخدمة: ${data.tools.join('، ')}` : 'لم تُستخدم أدوات';
  } catch (error) {
    answer.classList.add('error');
    answer.textContent = error.message;
  } finally {
    send.disabled = false;
  }
}

send.addEventListener('click', ask);
message.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') ask();
});
document.querySelectorAll('[data-example]').forEach((button) => {
  button.addEventListener('click', () => { message.value = button.dataset.example; message.focus(); });
});
