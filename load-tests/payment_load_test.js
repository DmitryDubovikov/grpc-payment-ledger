import grpc from 'k6/net/grpc';
import { check, sleep } from 'k6';
import { uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';
import { Counter, Trend } from 'k6/metrics';

const client = new grpc.Client();
client.load(['../proto'], 'payment/v1/payment.proto');

// Custom metrics
const paymentAuthorized = new Counter('payment_authorized');
const paymentDeclined = new Counter('payment_declined');
const paymentDuplicate = new Counter('payment_duplicate');
const paymentDuration = new Trend('payment_duration_ms');

export const options = {
  scenarios: {
    // Smoke test - minimal load
    smoke: {
      executor: 'constant-vus',
      vus: 1,
      duration: '30s',
      startTime: '0s',
      gracefulStop: '5s',
    },
    // Load test - normal load
    load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 10 },   // Ramp up
        { duration: '1m', target: 50 },    // Stay at 50 users
        { duration: '30s', target: 100 },  // Peak load
        { duration: '30s', target: 0 },    // Ramp down
      ],
      startTime: '30s',
      gracefulRampDown: '10s',
    },
    // Stress test - high load
    stress: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 200 },
        { duration: '5m', target: 200 },
        { duration: '2m', target: 0 },
      ],
      startTime: '3m',
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    'grpc_req_duration': ['p(95)<500', 'p(99)<1000'],
    'payment_duration_ms': ['p(95)<400', 'p(99)<800'],
    'checks': ['rate>0.95'],
  },
};

const PAYER_IDS = ['acc-payer-001'];
const PAYEE_IDS = ['acc-payee-002'];

export default function() {
  client.connect('localhost:50051', { plaintext: true });

  const payerId = PAYER_IDS[Math.floor(Math.random() * PAYER_IDS.length)];
  let payeeId = PAYEE_IDS[Math.floor(Math.random() * PAYEE_IDS.length)];

  // Ensure payer and payee are different
  while (payeeId === payerId) {
    payeeId = PAYEE_IDS[Math.floor(Math.random() * PAYEE_IDS.length)];
  }

  const request = {
    idempotency_key: uuidv4(),
    payer_account_id: payerId,
    payee_account_id: payeeId,
    amount_cents: Math.floor(Math.random() * 1000) + 100,
    currency: 'USD',
    description: 'Load test payment',
  };

  const startTime = Date.now();
  const response = client.invoke(
    'payment.v1.PaymentService/AuthorizePayment',
    request
  );
  const duration = Date.now() - startTime;

  paymentDuration.add(duration);

  const isSuccess = check(response, {
    'status is OK': (r) => r && r.status === grpc.StatusOK,
    'payment processed': (r) => {
      if (!r || !r.message) return false;
      const status = r.message.status;
      return ['PAYMENT_STATUS_AUTHORIZED', 'PAYMENT_STATUS_DECLINED', 'PAYMENT_STATUS_DUPLICATE'].includes(status);
    },
  });

  if (isSuccess && response.message) {
    switch (response.message.status) {
      case 'PAYMENT_STATUS_AUTHORIZED':
        paymentAuthorized.add(1);
        break;
      case 'PAYMENT_STATUS_DECLINED':
        paymentDeclined.add(1);
        break;
      case 'PAYMENT_STATUS_DUPLICATE':
        paymentDuplicate.add(1);
        break;
    }
  }

  client.close();
  sleep(0.1);
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'load-tests/results/summary.json': JSON.stringify(data),
  };
}

function textSummary(data, opts) {
  const checks = data.metrics.checks;
  const duration = data.metrics.grpc_req_duration;
  const paymentDur = data.metrics.payment_duration_ms;

  let output = `
================================================================================
                           PAYMENT LOAD TEST RESULTS
================================================================================

SUMMARY
-------
Total Requests:    ${data.metrics.iterations ? data.metrics.iterations.values.count : 'N/A'}
Duration:          ${data.state.testRunDurationMs / 1000}s

RESPONSE TIMES (grpc_req_duration)
----------------------------------
  avg:  ${duration ? duration.values.avg.toFixed(2) : 'N/A'}ms
  min:  ${duration ? duration.values.min.toFixed(2) : 'N/A'}ms
  max:  ${duration ? duration.values.max.toFixed(2) : 'N/A'}ms
  p(95): ${duration ? duration.values['p(95)'].toFixed(2) : 'N/A'}ms
  p(99): ${duration ? duration.values['p(99)'].toFixed(2) : 'N/A'}ms

PAYMENT DURATION
----------------
  avg:  ${paymentDur ? paymentDur.values.avg.toFixed(2) : 'N/A'}ms
  p(95): ${paymentDur ? paymentDur.values['p(95)'].toFixed(2) : 'N/A'}ms
  p(99): ${paymentDur ? paymentDur.values['p(99)'].toFixed(2) : 'N/A'}ms

PAYMENT STATUS
--------------
  Authorized: ${data.metrics.payment_authorized ? data.metrics.payment_authorized.values.count : 0}
  Declined:   ${data.metrics.payment_declined ? data.metrics.payment_declined.values.count : 0}
  Duplicate:  ${data.metrics.payment_duplicate ? data.metrics.payment_duplicate.values.count : 0}

CHECKS
------
  Success Rate: ${checks ? (checks.values.rate * 100).toFixed(2) : 'N/A'}%

THRESHOLDS
----------
${Object.entries(data.metrics)
  .filter(([name]) => data.options.thresholds && data.options.thresholds[name])
  .map(([name, metric]) => {
    const thresholds = data.options.thresholds[name];
    return thresholds.map(t => `  ${name} ${t}: ${metric.thresholds[t] ? '✓ PASSED' : '✗ FAILED'}`).join('\n');
  })
  .join('\n')}

================================================================================
`;
  return output;
}
