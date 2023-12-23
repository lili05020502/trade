const moneyInput = document.getElementById("moneyInput");
const initialAssetValue = document.getElementById("initialAssetValue");
const portvalue = document.getElementById("portvalue");
const tradeOutput = document.getElementById("tradeoutput");


moneyInput.addEventListener("input", function () {
    initialAssetValue.textContent = moneyInput.value;
});
init();
function init() {
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('end_dateInput').setAttribute('max', today);
    get_stock_top();
}
function get_stock_top() {
    fetch('/api/stocktop')
        .then(response => response.json())
        .then(data => {
             
            // console.log(data);
            const stockListDiv = document.getElementById('stockList');
                data.forEach(stock => {
                    const stockTopItem=document.createElement('div');
                    const stockName = document.createElement('p');
                    const stockCode = document.createElement('p');
                    stockName.classList.add('stockName');
                    stockCode.classList.add('stockCode');
                    stockName.textContent = `${stock.name}`;
                    stockCode.textContent = `${stock.code}`;
                    stockTopItem.appendChild(stockName);
                    stockTopItem.appendChild(stockCode);
                    stockListDiv.appendChild(stockTopItem);
                });
                stockListDiv.addEventListener('click', function(event) {
                    
                    if (event.target.classList.contains('stockCode') || event.target.classList.contains('stockName')) {
                        
                        const clickedStockCode = event.target.parentNode.querySelector('.stockCode').textContent.trim();
                        const symbolInput = document.getElementById('symbolinput');
                        symbolInput.value = clickedStockCode;
                    }
                });
        })
}
function sendBacktest() {
    const today = new Date();
    const symbol = document.getElementById('symbolinput').value;
    const strategy = document.getElementById('strategyinput').value;
    const money = document.getElementById('moneyInput').value;
    const commission = document.getElementById('commissionInput').value;
    const startDate = document.getElementById('star_dateInput').value;
    const endDate = document.getElementById('end_dateInput').value;

    const sharesInput = document.getElementById("sharesInput");
    const sharesPerTrade = parseInt(sharesInput.value);
    const portValueElement = document.getElementById('portValueElement')
    const tableBody = document.querySelector("#tradeTable tbody");
    if (symbol === "") {
        alert("請輸入股票代號");
        return;
    }

    if (strategy === "") {
        alert("請選擇回測策略");
        return;
    }

    if (money === "") {
        alert("輸入初始資金");
        return;
    }
    if (sharesInput === "") {
        alert("輸入下單股數");
        return;
    }
    if (sharesPerTrade < 0){
        alert("下單股數不能為負");
        return;
    }
    if (sharesPerTrade === 0){
        alert("下單股數不能為0");
        return;
    }

    if (commission === "") {
        alert("輸入交易費率");
        return;
    }
    if (commission< 0) {
        alert("交易費率不能為負");
        return;
    }


    if (startDate === "") {
        alert("選擇回測開始日期");
        return;
    }

    if (endDate === "") {
        alert("選擇回測結束日期");
        return;
    }
    const startDateverify = new Date(startDate);
    const endDateverify = new Date(endDate);


    const twoMonthsLater = new Date(startDateverify);
    twoMonthsLater.setMonth(startDateverify.getMonth() + 2);


    if (endDateverify < twoMonthsLater) {
        alert("回測區間需大於兩個月");
        return;
    }
    console.log("endDateverify:", endDateverify, "today:", today)
    if (endDateverify > today) {
        alert("結束日期不能超過今天");
        return;
    }
    tradeOutput.innerHTML = '';
    tableBody.innerHTML = '';
    portValueElement.innerHTML = '';
    portvalue.innerHTML = '';
    
    const loadingSpinner = document.getElementById('loadingSpinner');
    loadingSpinner.style.display = 'block';

    const formData = {
        symbol: symbol,
        strategy: strategy,
        money: money,
        commission: commission,
        startDate: startDate,
        endDate: endDate,
        sharesPerTrade: sharesPerTrade
    };
    console.log(formData)

    fetch('/backtest', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
    })
        .then(response => response.json())
        .then(data => {
            console.log(data)

            const port_value = data.port_value;
            const s3url = data.tranderoutput_url;
            const traderecords = data.trade_records;
            console.log(port_value);
            portvalue.textContent = Math.floor(port_value);
            tradeOutput.innerHTML = '';

            loadingSpinner.style.display = 'none';

            img = document.createElement('img');
            img.classList.add('tradeoutputimg')
            img.src = s3url;
            tradeOutput.appendChild(img);

            const return_rate_formatted = data.return_rate_formatted;
            console.log("return_rate_formatted:", return_rate_formatted)

            // const OverallReturn = calculateOverallReturn(money, Math.floor(port_value));
            // console.log("OverallReturn:", OverallReturn);


            const arrow = return_rate_formatted >= 0 ? '↑' : '↓';
            const color = return_rate_formatted >= 0 ? 'red' : 'green';

            
            portValueElement.innerHTML = `<span style="color: ${color};">${arrow} ${Math.abs(return_rate_formatted).toFixed(2)}%</span>`;

            traderecords.forEach(record => {
                const row = document.createElement('tr');
                const actionCell = document.createElement('td');
                const datetimeCell = document.createElement('td');
                const priceCell = document.createElement('td');

                actionCell.textContent = record.action;
                // datetimeCell.textContent = formatDate(record.datetime);
                datetimeCell.textContent = record.datetime;
                priceCell.textContent = record.price;

                row.appendChild(actionCell);
                row.appendChild(datetimeCell);
                row.appendChild(priceCell);

                tableBody.appendChild(row);
            });
        })
        .catch(error => {
            console.error('Error:', error);
            loadingSpinner.style.display = 'none';
        });
}

function formatDate(inputDate) {
    const options = { year: 'numeric', month: '2-digit', day: '2-digit' };
    const date = new Date(inputDate);
    return date.toLocaleDateString('en-US', options);
}

// function calculateOverallReturn(initialCapital, finalCapital) {
//     // 計算整體報酬率
//     const overallReturn = ((finalCapital - initialCapital) / initialCapital) * 100;

//     return overallReturn;
// }






