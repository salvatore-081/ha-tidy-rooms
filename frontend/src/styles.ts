// Shared styles. Only Home Assistant theme variables, with fallbacks, so the
// panel follows the user's theme in light and dark mode.

import { css } from "lit";

export const tokens = css`
  :host {
    --tr-gap: 16px;
    --tr-radius: var(--ha-card-border-radius, 12px);
    --tr-card-bg: var(--card-background-color, var(--ha-card-background, #fff));
    --tr-border: var(--divider-color, rgba(0, 0, 0, 0.12));
    --tr-text: var(--primary-text-color, #212121);
    --tr-muted: var(--secondary-text-color, #727272);
    --tr-primary: var(--primary-color, #03a9f4);
    --tr-on-primary: var(--text-primary-color, #fff);
    --tr-success: var(--success-color, #43a047);
    --tr-warning: var(--warning-color, #ffa600);
    --tr-error: var(--error-color, #db4437);
    --tr-info: var(--info-color, #039be5);
    --tr-off: var(--disabled-text-color, #bdbdbd);
  }
`;

export const shared = css`
  .card {
    background: var(--tr-card-bg);
    border-radius: var(--tr-radius);
    border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--tr-border));
    box-shadow: var(--ha-card-box-shadow, none);
    color: var(--tr-text);
  }
  .card-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px 16px 0;
    font-size: 1.1rem;
    font-weight: 500;
  }
  .card-content {
    padding: 16px;
  }
  .muted {
    color: var(--tr-muted);
  }
  .row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .spacer {
    flex: 1;
  }

  /* Buttons */
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    min-height: 36px;
    padding: 0 14px;
    border-radius: 18px;
    border: 1px solid var(--tr-border);
    background: transparent;
    color: var(--tr-primary);
    font: inherit;
    font-weight: 500;
    font-size: 0.9rem;
    cursor: pointer;
    white-space: nowrap;
  }
  .btn:hover:not(:disabled) {
    background: color-mix(in srgb, var(--tr-primary) 8%, transparent);
  }
  .btn:focus-visible,
  .icon-btn:focus-visible,
  .tab:focus-visible {
    outline: 2px solid var(--tr-primary);
    outline-offset: 2px;
  }
  .btn:disabled {
    color: var(--tr-off);
    cursor: default;
  }
  .btn.filled {
    background: var(--tr-primary);
    border-color: var(--tr-primary);
    color: var(--tr-on-primary);
  }
  .btn.filled:hover:not(:disabled) {
    background: color-mix(in srgb, var(--tr-primary) 88%, black);
  }
  .btn.filled:disabled {
    background: var(--tr-off);
    border-color: var(--tr-off);
    color: var(--tr-on-primary);
  }
  .btn.danger {
    color: var(--tr-error);
  }
  .btn.danger.filled {
    background: var(--tr-error);
    border-color: var(--tr-error);
    color: #fff;
  }
  .btn ha-icon {
    --mdc-icon-size: 18px;
  }
  .icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: none;
    background: transparent;
    color: var(--tr-muted);
    cursor: pointer;
    padding: 0;
    flex: none;
  }
  .icon-btn:hover:not(:disabled) {
    background: color-mix(in srgb, var(--tr-text) 8%, transparent);
  }
  .icon-btn:disabled {
    color: var(--tr-off);
    cursor: default;
  }

  /* Status chips and tones */
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 10px 2px 8px;
    border-radius: 12px;
    font-size: 0.8rem;
    font-weight: 500;
    line-height: 20px;
    white-space: nowrap;
    color: var(--tone);
    background: color-mix(in srgb, var(--tone) 14%, transparent);
  }
  .chip ha-icon {
    --mdc-icon-size: 16px;
  }
  .tone-success {
    --tone: var(--tr-success);
  }
  .tone-active {
    --tone: var(--tr-info);
  }
  .tone-ready {
    --tone: var(--tr-primary);
  }
  .tone-waiting {
    --tone: var(--tr-muted);
  }
  .tone-warning {
    --tone: var(--tr-warning);
  }
  .tone-error {
    --tone: var(--tr-error);
  }
  .tone-off {
    --tone: var(--tr-off);
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
  .error-box {
    padding: 12px 16px;
    border-radius: 8px;
    color: var(--tr-error);
    background: color-mix(in srgb, var(--tr-error) 10%, transparent);
  }
  .empty-state {
    padding: 48px 16px;
    text-align: center;
    color: var(--tr-muted);
  }
  .empty-state ha-icon {
    --mdc-icon-size: 48px;
    color: var(--tr-off);
    display: block;
    margin: 0 auto 12px;
  }
`;
