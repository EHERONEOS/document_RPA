import axios from 'axios';

/** 统一响应包装（§5.2）：{code, message, data} */
export interface ApiEnvelope<T = unknown> {
  code: number;
  message: string;
  data: T;
}

/**
 * T0.3：axios 封装 —— baseURL 走 vite dev 代理（/api → 127.0.0.1:9000），
 * 响应拦截器统一解包 {code,data}，业务错误统一抛出。
 */
const http = axios.create({
  baseURL: '/api/v1',
  timeout: 15_000,
});

http.interceptors.response.use(
  (response) => {
    const envelope = response.data as ApiEnvelope;
    if (envelope && typeof envelope === 'object' && 'code' in envelope) {
      if (envelope.code !== 0) {
        return Promise.reject(new Error(envelope.message || `业务错误 code=${envelope.code}`));
      }
      // 直接把 data 交给调用方
      return envelope.data as never;
    }
    return response.data;
  },
  (error) => Promise.reject(error instanceof Error ? error : new Error(String(error))),
);

export default http;
