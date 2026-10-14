export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }

  toJSON() {
    return { __apiError: true, status: this.status, code: this.code, message: this.message }
  }

  static fromJSON(data: unknown): ApiError | null {
    if (
      typeof data === 'object' &&
      data !== null &&
      (data as Record<string, unknown>).__apiError === true
    ) {
      const d = data as { status: number; code: string; message: string }
      return new ApiError(d.status, d.code, d.message)
    }
    return null
  }
}
