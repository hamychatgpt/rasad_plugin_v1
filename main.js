/**
 * اسکریپت اصلی برنامه
 */

// نمایش پیام‌های هشدار
function showAlert(message, type = 'success', container = 'body', timeout = 5000) {
    // ایجاد المان هشدار
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // افزودن به صفحه
    if (container === 'body') {
        // ایجاد یک کانتینر برای هشدارها اگر وجود ندارد
        let alertContainer = document.getElementById('alert-container');
        if (!alertContainer) {
            alertContainer = document.createElement('div');
            alertContainer.id = 'alert-container';
            alertContainer.className = 'position-fixed top-0 end-0 p-3';
            alertContainer.style.zIndex = '1050';
            document.body.appendChild(alertContainer);
        }
        alertContainer.appendChild(alertDiv);
    } else {
        // افزودن به کانتینر مشخص شده
        document.querySelector(container).appendChild(alertDiv);
    }
    
    // حذف خودکار بعد از مدت زمان مشخص
    if (timeout > 0) {
        setTimeout(() => {
            alertDiv.classList.remove('show');
            setTimeout(() => {
                alertDiv.remove();
            }, 150);
        }, timeout);
    }
    
    return alertDiv;
}

// تاییدیه حذف
function confirmDelete(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// تنظیم رویدادها
document.addEventListener('DOMContentLoaded', function() {
    // رویدادهای عمومی
    
    // بستن هشدارها با کلیک
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('btn-close') && e.target.closest('.alert')) {
            const alert = e.target.closest('.alert');
            alert.classList.remove('show');
            setTimeout(() => {
                alert.remove();
            }, 150);
        }
    });
    
    // دکمه‌های حذف با تاییدیه
    const deleteButtons = document.querySelectorAll('[data-confirm]');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            
            const message = this.getAttribute('data-confirm') || 'آیا از حذف این مورد اطمینان دارید؟';
            const href = this.getAttribute('href');
            
            confirmDelete(message, () => {
                window.location.href = href;
            });
        });
    });
    
    // تبدیل تاریخ‌ها به تاریخ فارسی - در نسخه‌های بعدی
});

// تابع برای ارسال درخواست‌های AJAX
async function sendRequest(url, method = 'GET', data = null, contentType = 'application/json') {
    try {
        const options = {
            method: method,
            headers: {
                'Content-Type': contentType
            }
        };
        
        if (data) {
            options.body = contentType === 'application/json' ? JSON.stringify(data) : data;
        }
        
        const response = await fetch(url, options);
        
        // بررسی وضعیت پاسخ
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'خطا در ارتباط با سرور');
        }
        
        return await response.json();
    } catch (error) {
        console.error('Error:', error);
        showAlert(error.message, 'danger');
        throw error;
    }
}