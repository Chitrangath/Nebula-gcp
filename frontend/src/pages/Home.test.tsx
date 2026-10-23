import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import Home from './Home'

describe('Home', () => {
  it('offers both sides of the Nebula journey', () => {
    render(<Home />)

    expect(screen.getByRole('heading', { name: 'Nebula AI Cloud' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Submit a Job' })).toHaveAttribute('href', '/user/submit')
    expect(screen.getByRole('link', { name: 'Become a Provider' })).toHaveAttribute(
      'href',
      '/provider/register',
    )
  })
})
