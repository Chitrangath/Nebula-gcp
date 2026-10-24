import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import Navbar from './Navbar'

vi.mock('./WalletConnect', () => ({ default: () => <button type="button">Connect Wallet</button> }))

describe('Navbar', () => {
  it('keeps navigation operable through the compact mobile menu', async () => {
    render(<MemoryRouter><Navbar /></MemoryRouter>)

    const menu = screen.getByRole('button', { name: 'Open navigation' })
    expect(menu).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(menu)

    expect(screen.getByRole('button', { name: 'Close navigation' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByRole('link', { name: 'Network' })).toHaveLength(2)
    await userEvent.click(screen.getAllByRole('link', { name: 'Network' })[1])
    expect(screen.getByRole('button', { name: 'Open navigation' })).toHaveAttribute('aria-expanded', 'false')
  })
})
